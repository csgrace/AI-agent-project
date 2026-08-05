"""Script automation agent — helps users create, manage, and execute Python scripts."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.messages import BaseMessage

from ...core.global_state import get_script_sandbox_dir, get_skill_registry, set_script_sandbox_dir
from ..agent_factory import build_agent
from ..middleware import handle_tool_error
from ..agent_runner import AgentRunner
from .tools import default_script_tools


SCRIPT_SYSTEM_PROMPT = """You are a helpful script automation assistant.
You help users create, manage, and execute Python automation scripts in a safe sandbox environment.
Use tools whenever script data is needed or updated.
When the user goal is complete, start your response with 'FINISH:' and provide a short summary.
If a tool fails, read the tool error and try a corrected tool call.

Workflow guidelines:
1. Understand the user's requirement before creating a script. Ask clarifying questions if needed.
2. Create the script using create_script tool with a meaningful name, clear description, and proper category.
3. If the script needs third-party packages, install them first using install_sandbox_package.
4. Execute the script using execute_script to verify it works.
5. If execution fails, read the error, fix the script using update_script, and re-run.
6. Iterate until the script works correctly.

Sandbox environment:
- Sandbox working directory: {sandbox_dir}
- User scripts are stored in {sandbox_dir}/.scripts/ (each script as a .py file)
- A dedicated virtual environment (.venv) is automatically created under {sandbox_dir}/ when first needed, and reused on subsequent runs
- When executing a script, a temporary wrapper file (._wrapper_*.py) is generated in {sandbox_dir}/ to enforce security policies, and is cleaned up after execution
- Scripts run with their current working directory (cwd) set to {sandbox_dir}
- A .trash directory is automatically created under {sandbox_dir}/.trash/ to hold files/directories that were "deleted" by the script

Rules:
1. Scripts run in a sandboxed environment. Dangerous operations (subprocess, eval, etc.) are automatically blocked.
2. All delete operations (os.remove, os.unlink, os.rmdir, os.removedirs, shutil.rmtree) are intercepted: instead of actually deleting, the file/directory is moved to {sandbox_dir}/.trash/ with a unique suffix to avoid name conflicts. Users can recover files from .trash if needed.
3. Always check if a script already exists before creating a new one with the same name.
4. Provide clear explanations of what each script does, especially when listing scripts.
5. You must provide thinking output that shows your reasoning process. The thinking should be concise, to the point, and different from your final answer.
"""


def _build_middleware(model, summary_trigger: int, summary_keep: int):
    """Build the middleware pipeline for the script automation agent."""
    return [
        SummarizationMiddleware(
            model=model,
            trigger=("messages", summary_trigger),
            keep=("messages", summary_keep),
        ),
        handle_tool_error,
    ]


class ScriptAutomationAgent:
    """A script automation agent wrapper powered by create_agent runtime."""

    def __init__(
        self,
        model,
        *,
        max_steps: int = 10,
        system_prompt: str = SCRIPT_SYSTEM_PROMPT,
        tools: Optional[List[Any]] = None,
        summary_trigger: int = 36,
        summary_keep: int = 14,
        history_path: Optional[Path] = None,
    ) -> None:
        self.model = model
        self.max_steps = max_steps
        self.tools = tools or default_script_tools()

        # Store raw init params so rebuild() can recreate the agent.
        self._init_kwargs = dict(
            max_steps=max_steps,
            system_prompt=system_prompt,  # raw template with {sandbox_dir}
            tools=self.tools,
            summary_trigger=summary_trigger,
            summary_keep=summary_keep,
        )
        self._history_path = history_path

        self._build_compiled_agent()

        # Restore persisted conversation history, if available.
        if history_path is not None:
            restored = AgentRunner.load_history(history_path)
            if restored:
                self.runner.messages = restored
                self.messages = self.runner.messages

    def reinitialize(self, new_model) -> None:
        """Replace the underlying LLM without losing conversation history."""
        existing_messages = list(getattr(self.runner, "messages", []))
        self.model = new_model
        self._build_compiled_agent()
        if existing_messages:
            self.runner.messages = existing_messages
            self.messages = self.runner.messages

    def _build_compiled_agent(self) -> None:
        """(Re)build the compiled LangChain agent from stored params + current sandbox_dir."""
        # Inject sandbox directory into system prompt
        sandbox_path = get_script_sandbox_dir()
        raw_prompt: str = self._init_kwargs["system_prompt"]
        if sandbox_path:
            injected_prompt = raw_prompt.format(sandbox_dir=sandbox_path)
        else:
            injected_prompt = raw_prompt.replace("{sandbox_dir}", "(not yet initialized)")

        # Build middleware with custom trigger/keep values.
        middleware = _build_middleware(
            self.model,
            self._init_kwargs["summary_trigger"],
            self._init_kwargs["summary_keep"],
        )

        compiled_agent = build_agent(
            self.model,
            tools=self.tools,
            system_prompt=injected_prompt,
            skill_registry=get_skill_registry(),
            middleware=middleware,
        )
        self.runner = AgentRunner(compiled_agent, max_steps=self.max_steps)
        self.messages: List[BaseMessage] = self.runner.messages

    def rebuild(self) -> ScriptAutomationAgent:
        """Create a new agent instance for the *current* sandbox_dir in global state.

        The new agent starts with an empty conversation. The old agent's messages
        are discarded (caller should save them first if needed).

        Returns:
            A fresh ``ScriptAutomationAgent`` with the same model/tools/settings.
        """
        new_agent = ScriptAutomationAgent(
            self.model,
            **self._init_kwargs,
            history_path=None,  # new sandbox → fresh conversation
        )
        return new_agent

    def run_turn(self, user_text: str) -> Dict[str, Any]:
        """Run one user turn through create_agent runtime."""
        result = self.runner.run_turn(user_text)
        self.messages = self.runner.messages
        return result

    def run_turn_stream(self, user_text: str) -> Generator[Dict[str, Any], None, None]:
        """Run one user turn and yield streaming runtime events."""
        for event in self.runner.run_turn_stream(user_text):
            self.messages = self.runner.messages
            yield event


def initialize_script_state(sandbox_dir: Optional[Path] = None) -> Path:
    """Initialize the script sandbox directory in global state.

    Args:
        sandbox_dir: Path to the sandbox working directory.
                     Defaults to ``<project_root>/resources/user_scripts/``.

    Returns:
        The resolved sandbox directory path.
    """
    if sandbox_dir is None:
        # Default to <project_root>/resources/user_scripts/
        sandbox_dir = Path(__file__).resolve().parents[3] / "resources" / "user_scripts"
        resolved = sandbox_dir.resolve()
        resolved.mkdir(parents=True, exist_ok=True)
    else:
        resolved = sandbox_dir.resolve()
        if not resolved.exists():
            raise FileNotFoundError(
                f"Script sandbox directory does not exist: {resolved}"
            )
        if not resolved.is_dir():
            raise NotADirectoryError(
                f"Script sandbox path is not a directory: {resolved}"
            )

    set_script_sandbox_dir(str(resolved))
    return resolved
