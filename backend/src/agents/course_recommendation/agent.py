"""Course recommendation agent powered by the shared create_agent runtime."""

from __future__ import annotations

from typing import Any, Dict, Generator, List, Optional

from langchain_core.messages import BaseMessage

from ..agent_factory import build_agent
from ..agent_runner import AgentRunner


COURSE_RECOMMENDATION_SYSTEM_PROMPT = """You are a course recommendation agent for a university planning assistant.
Your job is to generate a structured course plan from the provided student profile, completed courses, target term, and available course offerings.

Rules:
1. Do not use any local scoring code or hard-coded recommendation tables.
2. Base the recommendation on the provided JSON context only.
3. Prefer courses that fit the student's major, interests, career goal, recommendation note, and remaining graduation needs.
4. Avoid recommending courses already completed or clearly conflicting with the target term schedule.
5. If the available course offering list is incomplete, explain that uncertainty in warnings instead of inventing courses.
6. When searching the full course table, do not require exact literal matches;
  use course code, name fragments, Chinese/English aliases, instructor names,
  and teaching class numbers as fuzzy match cues.
7. Return exactly one JSON object and nothing else.

Output schema:
{
  "term": {"term_id": str, "year": int, "semester": int, "label": str, "status": str},
  "recommended_courses": [
    {"course_id": str|null, "course_name": str, "credits": number|null, "score": number, "reason": str|null, "status": str, "source": str}
  ],
  "postponed_courses": [
    {"course_id": str|null, "course_name": str, "credits": number|null, "score": number, "reason": str|null, "status": str, "source": str}
  ],
  "meetings": [
    {"course_id": str|null, "course_name": str, "instructor": str|null, "location": str|null, "day_of_week": int, "start_slot": int, "end_slot": int, "weeks": str|null, "credits": number|null, "source": str, "metadata": object}
  ],
  "warnings": [str],
  "rationale": str,
  "graduation_check": {"status": str, "summary": str, "missing_courses": [str]}
}

Scoring guidance:
1. Use scores in the 0-100 range.
2. Highest scores should reflect the best fit among the available options.
3. Each course's `reason` must be a complete, fluent Chinese sentence (20 characters or fewer) explaining why this course fits the student.
   Example: "核心AI课程，匹配机器学习兴趣" instead of "匹配兴趣: 机器学习".
4. The top-level `rationale` should be 2-3 concise Chinese sentences summarizing the overall recommendation strategy.
5. If no suitable course is found, return empty recommendation lists and explain why.
"""


class CourseRecommendationAgent:
    """A recommendation agent wrapper built on the shared LangChain runtime."""

    def __init__(
        self,
        model,
        *,
        max_steps: int = 2,
        system_prompt: str = COURSE_RECOMMENDATION_SYSTEM_PROMPT,
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
            middleware=[],
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
            middleware=[],
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