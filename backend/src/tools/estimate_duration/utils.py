"""Utilities for estimating event durations in minutes."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from ...models.calendar.calendar_event import CalendarEvent
from ...services.llm_config import LLMConfig
from ..shared_utils.memory_adapter import MemoryAdapter


DEFAULT_TOP_K_MEMORY = 3
ENABLE_MEMORY_CONTEXT = False


class DurationEstimationResult(BaseModel):
    """Structured result returned by LLM duration estimation."""

    duration_minutes: int = Field(..., ge=1, le=24 * 60, description="Estimated duration in minutes")
    reason: str = Field(..., description="A short rationale for the estimation")


SYSTEM_PROMPT = """You estimate the duration of a calendar event.

Rules:
1. Return duration in minutes only.
2. Use the event title, description, time span, and memory context.
3. Use the information in title and description first. Then use common sense related to the title (e.g. title is "SAT exam", we know its duration is 134 minutes). Use time span (deadline - scheduled_start) as the last hint because in some cases it is not reliable (e.g. the span is 2 weeks but actually it is the span from the assignment release to the deadline, and the actual working time is around 3 hours).
4. If uncertain, choose a practical default value rather than refusing.
5. Keep reason concise.
6. Output must follow the structured format instructions exactly.
"""


EVENT_TEMPLATE = """
Event:
- id: {event_id}
- title: {title}
- description: {description}
- scheduled_start: {scheduled_start}
- deadline: {deadline}
- category: {category}

Memory context:
{memory_context}

User hint:
{user_hint}
"""


def estimate_event_durations(
    events: List[CalendarEvent],
    memory_adapter: Optional[MemoryAdapter] = None,
    user_hint: Optional[str] = None,
    missing_only: bool = True,
) -> List[CalendarEvent]:
    """Estimate duration for events and write to event.duration in minutes.

    Duration is estimated in minutes and stored in minutes.
    """
    adapter = memory_adapter or MemoryAdapter()
    llm = _build_llm()

    updated_events: List[CalendarEvent] = []
    for event in events:
        if missing_only and event.duration is not None:
            updated_events.append(event)
            continue

        memory_items = adapter.query_context(event=event, top_k=DEFAULT_TOP_K_MEMORY) if ENABLE_MEMORY_CONTEXT else []
        memory_context = _format_memory_context(memory_items)

        minutes = _estimate_minutes_with_llm(
            llm=llm,
            event=event,
            memory_context=memory_context,
            user_hint=user_hint,
        )
        source = "llm"

        if minutes is None:
            minutes = _fallback_minutes(event)
            source = "fallback"

        event.duration = int(minutes)
        event.metadata = dict(event.metadata or {})
        # event.metadata["estimated_duration_minutes"] = int(minutes)
        # event.metadata["duration_estimation_source"] = source
        # event.metadata["duration_memory_items_count"] = len(memory_items)
        # event.metadata["duration_memory_enabled"] = ENABLE_MEMORY_CONTEXT

        updated_events.append(event)

    return updated_events


def _build_llm() -> Optional[ChatOpenAI]:
    cfg = LLMConfig.get_instance()
    return cfg.build_chat_model(tier="lightweight")


def _estimate_minutes_with_llm(
    llm: Optional[ChatOpenAI],
    event: CalendarEvent,
    memory_context: str,
    user_hint: Optional[str],
) -> Optional[int]:
    if llm is None:
        return None

    parser = PydanticOutputParser(pydantic_object=DurationEstimationResult)
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT + "\n\n{format_instructions}"),
        ("human", EVENT_TEMPLATE),
    ]).partial(format_instructions=parser.get_format_instructions())
    chain = prompt_template | llm | parser

    try:
        result = chain.invoke(
            {
                "event_id": event.id,
                "title": event.title,
                "description": event.description or "No description",
                "scheduled_start": event.scheduled_start.strftime("%Y-%m-%d %H:%M"),
                "deadline": event.deadline.strftime("%Y-%m-%d %H:%M"),
                "category": event.category.value,
                "memory_context": memory_context,
                "user_hint": user_hint or "No additional hint",
            }
        )
        return int(result.duration_minutes)
    except Exception as exc:
        print(f"Warning: duration estimation with LLM failed for event {event.id}: {exc}")
        return None


def _fallback_minutes(event: CalendarEvent) -> int:
    # If event has explicit time bounds, use them as deterministic fallback.
    delta_minutes = int((event.deadline - event.scheduled_start).total_seconds() / 60)
    if delta_minutes > 0:
        return delta_minutes

    title = (event.title or "").lower()
    if any(token in title for token in ["exam", "final", "midterm"]):
        return 120
    if any(token in title for token in ["quiz", "test"]):
        return 45
    if any(token in title for token in ["meeting", "standup"]):
        return 60
    if any(token in title for token in ["class", "lecture", "lab"]):
        return 90
    if any(token in title for token in ["assignment", "homework", "project"]):
        return 120
    return 60


def _format_memory_context(items: List[Dict[str, Any]]) -> str:
    if not items:
        return "No memory context available"

    lines: List[str] = []
    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. {item}")
    return "\n".join(lines)
