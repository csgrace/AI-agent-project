"""Learning assistant agent — chat-driven document summarization and quiz generation.

Powered by the create_agent runtime from agents/agent_factory.
"""

from __future__ import annotations

from typing import Any, Dict, Generator, List, Optional

from langchain_core.messages import BaseMessage

from ..agent_factory import build_agent, build_runtime_system_prompt
from ..agent_runner import AgentRunner
from .tools import generate_questions, list_supported_formats, summarize_document


LEARNING_ASSISTANT_SYSTEM_PROMPT = """You are a helpful learning assistant that helps students study course materials.
You have access to tools that can summarize documents and generate quiz questions.

How to respond:
1. When a user asks to summarize a document or generate questions, use the appropriate tool.
2. The user will tell you the file name after uploading it. Use the file name (e.g. "lecture1.pptx") as the file_path parameter.
3. Always explain what you're going to do before calling a tool.

Important - Quiz mode:
When generate_questions returns JSON with "_type": "quiz", the frontend will automatically render an interactive quiz. Do NOT repeat all questions in your reply. Just give a brief message like "已为您生成 X 道题目，请在下方的答题卡中作答。" and summarize the metadata (type, difficulty).

Important - Summary mode:
When summarize_document returns text, present the summary clearly. The full summary content is important.

Available summary styles: concise (简洁), detailed (详细), outline (要点提纲), mind_map (思维导图)
Available question types: multiple_choice (单选题), fill_in_blank (填空题), true_false (判断题), short_answer (简答题)
Available difficulty levels: easy (简单), medium (中等), hard (困难)

When the user's request is complete, start your response with 'FINISH:' and provide a short summary of what was done.
"""


def _build_default_tools():
    return [summarize_document, generate_questions, list_supported_formats]


class LearningAssistantAgent:
    """A learning assistant agent powered by create_agent runtime."""

    def __init__(
        self,
        model,
        *,
        max_steps: int = 8,
        system_prompt: str = LEARNING_ASSISTANT_SYSTEM_PROMPT,
        tools: Optional[List[Any]] = None,
    ) -> None:
        self.model = model
        self.max_steps = max_steps
        self.tools = tools or _build_default_tools()
        self._system_prompt = system_prompt

        self._build_compiled_agent()

    def _build_compiled_agent(self) -> None:
        """(Re)build the compiled LangChain agent."""
        compiled_agent = build_agent(
            self.model,
            tools=self.tools,
            system_prompt=self._system_prompt,
            middleware=[],  # no summarisation needed for this agent
        )
        self.runner = AgentRunner(compiled_agent, max_steps=self.max_steps)
        self.messages: List[BaseMessage] = self.runner.messages

    def reinitialize(self, new_model) -> None:
        """Replace the underlying LLM without losing conversation history."""
        existing_messages = list(getattr(self.runner, "messages", []))
        self.model = new_model
        self._build_compiled_agent()
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
