"""LLM-based event category judgment utilities."""
from typing import List, Optional
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from ...models.calendar.calendar_event import CalendarEvent
from ...models.calendar.enums import EventCategory
from ...services.llm_config import LLMConfig


# ── Lazy LLM initializer ──────────────────────────────────────────────
_cached_llm: Optional[ChatOpenAI] = None
_cached_version: int = -1


def _get_llm() -> Optional[ChatOpenAI]:
    """Get a lightweight-tier ChatOpenAI, rebuilding if the config changed."""
    global _cached_llm, _cached_version
    cfg = LLMConfig.get_instance()
    version = cfg.get_version()
    if _cached_llm is None or _cached_version < version:
        _cached_llm = cfg.build_chat_model(tier="lightweight")
        _cached_version = version
    return _cached_llm


class EventMatchResult(BaseModel):
    """Result of event matching with LLM."""
    category: EventCategory = Field(..., description="Which kind of category it is")


SYSTEM_PROMPT = """You are an event matching assistant. Your task is to determine the category of a calendar event.

Given an event and a user prompt, determine the event's category.

Rules:
1. Consider the event title, description, and any other relevant information.
2. The category has four options: BACKGROUND, SOLID, SCHEDULABLE, IGNORED.
    - BACKGROUND: These kind of events exist as background descriptions for a period of time, not schedulable and behave like a container. In most cases, they're some things like legal holiday, summer/winter vaction.
    - SOLID: These kind of events are tasks cannot be scheduled, such as conferences, classes and some fixed time activities.
    - SCHEDULABLE: These kind of events are tasks can change due time, like review plans, homework finished time.
    - IGNORED: These are events that should be filtered out based on the user prompt. For example, if the user says "Filter all events after 2026-3-1", then all events after that date should be marked as IGNORED.
3. IMPORTANT: You must NOT use the UNKNOWN category value. Always choose from BACKGROUND, SOLID, SCHEDULABLE, or IGNORED.
4. If the user prompt is not clear, set the category as BACKGROUND instead of IGNORED.
5. Follow the structure output guidance, don't mix other information like markdown in the output.
"""

EVENT_INFORMATION_TEMPLATE = """
Event Information:
- ID: {event_id}
- Title: {event_title}
- Description: {event_description}
- Scheduled Start: {scheduled_start}
- Deadline: {deadline}

User Prompt: {prompt}
"""


def check_event_matches_prompt(event: CalendarEvent, prompt: str) -> EventMatchResult:
    """Check a single event's category using LLM.
    
    Args:
        event: The calendar event to check
        prompt: The user's description/prompt
        
    Returns:
        EventMatchResult: The matching result with category
    """
    current_llm = _get_llm()
    if current_llm is None:
        raise RuntimeError("LLM not available — no API key configured")
    chain = prompt_template | current_llm | parser
    
    result = chain.invoke({
        "event_id": event.id,
        "event_title": event.title,
        "event_description": event.description or "No description",
        "scheduled_start": event.scheduled_start.strftime("%Y-%m-%d %H:%M"),
        "deadline": event.deadline.strftime("%Y-%m-%d %H:%M"),
        "prompt": prompt
    })
    
    return result


def judge_category_with_llm(events: List[CalendarEvent], prompt: str) -> List[CalendarEvent]:
    """Judge event categories using LLM batch processing.
    
    Args:
        events: List of events to judge
        prompt: The user's description/prompt
        
    Returns:
        List of events with their categories determined (including IGNORED ones)
    """
    parser = PydanticOutputParser(pydantic_object=EventMatchResult)
    
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT + "\n\n{format_instructions}"),
        ("human", EVENT_INFORMATION_TEMPLATE),
    ]).partial(format_instructions=parser.get_format_instructions())
    
    current_llm = _get_llm()
    if current_llm is None:
        raise RuntimeError("LLM not available — no API key configured")
    chain = prompt_template | current_llm | parser
    
    inputs = [
        {
            "event_id": event.id,
            "event_title": event.title,
            "event_description": event.description or "No description",
            "scheduled_start": event.scheduled_start.strftime("%Y-%m-%d %H:%M"),
            "deadline": event.deadline.strftime("%Y-%m-%d %H:%M"),
            "prompt": prompt
        }
        for event in events
    ]
    
    results = chain.batch(inputs)
    
    judged_events = []
    for event, result in zip(events, results):
        event.category = result.category
        judged_events.append(event)
    
    return judged_events
