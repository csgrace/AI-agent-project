"""Standalone script for real LLM duration estimation test.

Usage:
    python backend/src/tools/estimate_duration/real_model_test.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

# Ensure `src` is importable when running this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.models.calendar.calendar_event import CalendarEvent
from src.models.calendar.enums import EventCategory, EventSource
from src.tools.estimate_duration import utils as duration_utils


def main() -> None:
    # Requirement: disable memory query for this real-model test.
    duration_utils.ENABLE_MEMORY_CONTEXT = False

    event = CalendarEvent(
        id="000",
        title="四级考试",
        description=None,
        start_time=datetime(2026, 6, 13, 9, 0),
        end_time=datetime(2026, 6, 13, 11, 20),
        source=EventSource.UNIVERSITY,
        category=EventCategory.SOLID,
    )
    event_2 = CalendarEvent(
        id="001",
        title="6级考试",
        description=None,
        start_time=datetime(2026, 6, 13, 15, 0),
        end_time=datetime(2026, 6, 13, 17, 25),
        source=EventSource.UNIVERSITY,
        category=EventCategory.SOLID,
    )

    llm = duration_utils._build_llm()
    if llm is None:
        print("Model call skipped: DASHSCOPE_API_KEY is not set.")
        return

    parser = PydanticOutputParser(pydantic_object=duration_utils.DurationEstimationResult)
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", duration_utils.SYSTEM_PROMPT + "\n\n{format_instructions}"),
        ("human", duration_utils.EVENT_TEMPLATE),
    ]).partial(format_instructions=parser.get_format_instructions())

    chain = prompt_template | llm | parser

    print("=== Real Model Test Result ===")
    for current_event in [event, event_2]:
        result = chain.invoke(
            {
                "event_id": current_event.id,
                "title": current_event.title,
                "description": current_event.description or "No description",
                "start_time": current_event.start_time.strftime("%Y-%m-%d %H:%M"),
                "end_time": current_event.end_time.strftime("%Y-%m-%d %H:%M"),
                "category": current_event.category.value,
                "memory_context": "No memory context available",
                "user_hint": "No additional hint",
            }
        )

        print(f"event_id: {current_event.id}")
        print(f"title: {current_event.title}")
        print(f"duration_minutes: {result.duration_minutes}")
        print(f"reason: {result.reason}")
        print("---")


if __name__ == "__main__":
    main()
