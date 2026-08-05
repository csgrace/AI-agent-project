from typing import Dict, Any, List, Optional

from ..models.calendar.calendar_event import CalendarEvent
from ..models.calendar.calendar import Calendar
from ..models.calendar.draft_calendar import DraftCalendar
from ..models.calendar.enums import DirtyType
from .schemas import CalendarEventResponse, CalendarResponse, DraftCalendarResponse


def event_to_response(event: CalendarEvent) -> CalendarEventResponse:
    data = event.serialize_model()
    return CalendarEventResponse(**data)


def calendar_to_response(calendar: Calendar) -> CalendarResponse:
    events = [event_to_response(e) for e in calendar.events]
    return CalendarResponse(
        id=calendar.id,
        name=calendar.name,
        description=calendar.description,
        events=events,
        created_at=calendar.created_at.isoformat() if calendar.created_at else None,
        updated_at=calendar.updated_at.isoformat() if calendar.updated_at else None,
    )


def draft_to_response(draft: DraftCalendar) -> DraftCalendarResponse:
    events = [event_to_response(e) for e in draft.events]
    return DraftCalendarResponse(
        id=draft.id,
        events=events,
        dirty=draft.dirty.value if draft.dirty else None,
    )
