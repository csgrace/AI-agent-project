"""Minimal multi-round scheduler agent for demo usage."""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.messages import BaseMessage

from ...core.global_state import get_skill_registry, set_draft_calendar
from ...models.calendar.draft_calendar import DraftCalendar
from ...models.calendar.enums import DirtyType
from ...services.init_calendar.loader import init_calendar
from ...services.init_object_store.initializer import initialize_object_store
from ...services.skill_register import register_all_skills
from ..agent_factory import build_agent
from ..middleware import handle_tool_error
from ..agent_runner import AgentRunner
from .tools import default_demo_tools


SCHEDULER_SYSTEM_PROMPT = """You are a lightweight scheduler assistant.
Use tools whenever calendar data is needed or updated.
When the user goal is complete, start your response with 'FINISH:' and provide a short summary.
If a tool fails, read the tool error and try a corrected tool call.
Rules: 
1. All fetch tools are heavy and may cost a lot of times! Don't call them unless user explicitly ask you to fetch calendar data!
2. When users ask you to add some new events, you should distinguish the difference between computed_start_time and deadline. Computed_start_time is the time the event actually starts while the deadline is the latest time the event can be ended rather than its real end time(this is computed_end_time). Therefore, deadline may not equal to computed_start_time + duration.
3. The category has 3 type: background, solid and schedulable. Background events are used to be references like summer vacation. These events may have no relation to user. For example, teacher won't enjoy ungraduatees' vacation. In most case, they shouldn't be scheduled unless user explicitly requires. Solid events are those that have fixed time and user needs to attend like classes and import meeting. They shouldn't be scheduled with other events in the same time slot especially schedulabled events (in this special conflict cases, update operation will lead to error). Schedulable events are those that can be scheduled in any time slot as long as they can be finished before the deadline, such as doing homework and writing reports.
4. You must provide thinking output that shows your reasoning process. The thinking should be concise, to the point, and different from your final answer.
"""


def _build_middleware(model, summary_trigger: int, summary_keep: int):
    """Build the middleware pipeline for the scheduler agent."""
    return [
        SummarizationMiddleware(
            model=model,
            trigger=("messages", summary_trigger),
            keep=("messages", summary_keep),
        ),
        handle_tool_error,
    ]


class SchedulerDemoAgent:
    """A scheduler agent wrapper powered by create_agent runtime."""

    def __init__(
        self,
        model,
        *,
        max_steps: int = 8,
        system_prompt: str = SCHEDULER_SYSTEM_PROMPT,
        tools: Optional[List[Any]] = None,
        summary_trigger: int = 36,
        summary_keep: int = 14,
        history_path: Optional[Path] = None,
    ) -> None:
        self.model = model
        self.max_steps = max_steps
        self.tools = tools or default_demo_tools()

        # Store init params for later reinitialisation.
        self._init_kwargs = dict(
            max_steps=max_steps,
            system_prompt=system_prompt,
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

    def _build_compiled_agent(self) -> None:
        """(Re)build the compiled LangChain agent from stored params + current model."""
        kwargs = self._init_kwargs
        middleware = _build_middleware(self.model, kwargs["summary_trigger"], kwargs["summary_keep"])

        compiled_agent = build_agent(
            self.model,
            tools=kwargs["tools"],
            system_prompt=kwargs["system_prompt"],
            skill_registry=get_skill_registry(),
            middleware=middleware,
        )
        self.runner = AgentRunner(compiled_agent, max_steps=kwargs["max_steps"])
        self.messages: List[BaseMessage] = self.runner.messages

    def reinitialize(self, new_model) -> None:
        """Replace the underlying LLM without losing conversation history.

        Called by the settings API when the user changes API keys.
        """
        # Preserve existing messages
        existing_messages = list(getattr(self.runner, "messages", []))

        self.model = new_model
        self._build_compiled_agent()

        # Restore messages so conversation continuity is maintained
        if existing_messages:
            self.runner.messages = existing_messages
            self.messages = self.runner.messages

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


def initialize_demo_state(
    calendar_path: Optional[Path] = None,
    skills_dir: Optional[Path] = None,
) -> None:
    """Initialize object store and calendar/draft state for demo usage."""
    initialize_object_store()

    resolved_skills_dir = skills_dir
    if resolved_skills_dir is None:
        configured = os.getenv("AGENT_SKILLS_DIR", "").strip()
        if configured:
            resolved_skills_dir = Path(configured)
        else:
            resolved_skills_dir = Path(__file__).resolve().parents[2] / "skills"

    register_all_skills(str(resolved_skills_dir))

    calendar = init_calendar(calendar_path)

    cloned_events = [event.model_copy(deep=True) for event in calendar.events]
    draft = DraftCalendar(events=cloned_events, dirty=DirtyType.CLEAR)
    set_draft_calendar(draft)


def default_filter_window() -> Dict[str, str]:
    """Provide a default one-week filter window for prompting helpers."""
    now = datetime.now()
    end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    return {
        "start_time": now.isoformat(),
        "end_time": end.isoformat(),
    }
