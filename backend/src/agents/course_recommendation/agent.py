"""Course recommendation agent powered by the shared create_agent runtime.

Uses XML-structured system prompt for better instruction following and
multi-step tool execution (search → verify → validate → output).
"""

from __future__ import annotations

from typing import Any, Dict, Generator, List, Optional

from langchain_core.messages import BaseMessage

from ..agent_factory import build_agent
from ..agent_runner import AgentRunner
from .prompt_builder import COURSE_AGENT_SYSTEM_PROMPT


class CourseRecommendationAgent:
    """A recommendation agent wrapper built on the shared LangChain runtime."""

    def __init__(
        self,
        model,
        *,
        max_steps: int = 8,
        system_prompt: str = COURSE_AGENT_SYSTEM_PROMPT,
        tools: Optional[List[Any]] = None,
    ) -> None:
        self.model = model
        self.max_steps = max_steps
        self.tools = tools or []
        self._system_prompt = system_prompt

        compiled_agent = build_agent(
            model,
            tools=self.tools,
            system_prompt=system_prompt,
            middleware=None,
        )
        self.runner = AgentRunner(compiled_agent, max_steps=max_steps)
        self.messages: List[BaseMessage] = self.runner.messages

    def run_turn(self, user_text: str) -> Dict[str, Any]:
        """Run one recommendation turn and return the normalized reply payload."""
        result = self.runner.run_turn(user_text)
        self.messages = self.runner.messages
        return result

    def reinitialize(self, new_model) -> None:
        """Replace the underlying LLM without losing conversation history."""
        existing_messages = list(getattr(self.runner, "messages", []))
        self.model = new_model
        compiled_agent = build_agent(
            new_model,
            tools=self.tools,
            system_prompt=self._system_prompt,
            middleware=None,
        )
        self.runner = AgentRunner(compiled_agent, max_steps=self.max_steps)
        if existing_messages:
            self.runner.messages = existing_messages
            self.messages = self.runner.messages

    def run_turn_stream(self, user_text: str) -> Generator[Dict[str, Any], None, None]:
        """Run one recommendation turn and yield streaming runtime events."""
        for event in self.runner.run_turn_stream(user_text):
            self.messages = self.runner.messages
            yield event