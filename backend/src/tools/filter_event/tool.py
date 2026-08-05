"""Filter Event Tool for LangChain.

This tool provides functions for filtering calendar events based on time range and semantic prompts.
"""
from datetime import datetime
from langchain.tools import tool

from ...models.calendar.enums import EventStatus, EventCategory, DirtyType
from ...models.calendar.draft_calendar import DraftCalendar
from ...core.global_state import get_calendar, get_draft_calendar, set_draft_calendar, get_object_store


@tool
def filter_events(
    start_time: datetime,
    end_time: datetime
) -> str:
    """Filter calendar events by time range, category and status.
    
    This function retrieves events from the global calendar and filters them based on:
    1. Time range: Events whose end_time falls within the specified range
    2. Status: Only events with status PENDING or IN_PROGRESS
    
    The function filters events by time range and status, then writes the result
    into the unified draft calendar events list.
    
    Args:
        start_time: The start of the time range (inclusive). Events with end_time >= start_time will be included.
        end_time: The end of the time range (inclusive). Events with end_time <= end_time will be included.
        
    Returns:
        str: ObjectStore key pointing to ``List[CalendarEvent]`` that match criteria.
        The stored list can be empty.
        
    Raises:
        ValueError: If start_time is after end_time
    """
    if start_time > end_time:
        raise ValueError("start_time must be before or equal to end_time")

    object_store = get_object_store()
    
    calendar = get_calendar()
    if calendar is None:
        return object_store.put([], metadata={"kind": "calendar_event_list", "generated_by": "filter_events"})
    
    events = calendar.events
    
    time_filtered_events = [
        event for event in events
        if start_time <= event.deadline <= end_time
    ]
    
    status_filtered_events = [
        event for event in time_filtered_events
        if event.status in [EventStatus.PENDING, EventStatus.IN_PROGRESS]
    ]
        
    non_ignored_events = [event for event in status_filtered_events if event.category != EventCategory.IGNORED]
    
    draft_calendar = get_draft_calendar()
    if draft_calendar is None:
        draft_calendar = DraftCalendar()
    
    draft_calendar.update_events(non_ignored_events)
    draft_calendar.dirty = DirtyType.FETCH
    
    set_draft_calendar(draft_calendar)

    output_key = object_store.put(
        non_ignored_events,
        metadata={
            "kind": "calendar_event_list",
            "generated_by": "filter_events",
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
        },
    )
    return output_key


@tool
def filter_events_by_time_range_and_prompt(start_time: datetime, end_time: datetime) -> str:
    """Backward-compatible alias for filter_events."""
    return filter_events(start_time, end_time)
