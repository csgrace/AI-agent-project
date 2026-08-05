"""Utility functions for filter_event tool."""
from datetime import timedelta
from typing import List

from ...models.calendar.calendar_event import CalendarEvent
from ...models.calendar.simple_event import SimpleEvent
from ...models.calendar.enums import Priority, EventCategory


def convert_to_simple_event(event: CalendarEvent, category: EventCategory = None) -> SimpleEvent:
    """Convert a CalendarEvent to SimpleEvent format.
    
    Args:
        event: The CalendarEvent to convert
        category: Optional category override. If not provided, uses event's category
        
    Returns:
        SimpleEvent: The simplified event
    """
    default_duration = event.deadline - event.scheduled_start
    duration_value = timedelta(minutes=event.duration) if event.duration is not None else default_duration
    
    return SimpleEvent(
        id=event.id,
        title=event.title,
        description=event.description,
        start_time=event.scheduled_start,
        end_time=event.deadline,
        duration=duration_value,
        category=event.category,
        priority=event.priority or Priority.MEDIUM,
        color_tag=event.color_tag,
        location=event.location
    )
