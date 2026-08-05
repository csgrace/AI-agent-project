"""Utility functions for operator_calendar tool."""

import warnings
from datetime import datetime
from typing import Any, Dict, List, Optional

from ...core.global_state import get_calendar, get_draft_calendar, set_draft_calendar
from ...models.calendar.calendar_event import CalendarEvent
from ...models.calendar.draft_calendar import DraftCalendar
from ...models.calendar.enums import EventCategory, EventSource, EventStatus, Priority
from ...models.calendar.enums import DirtyType
from .schemas import CalendarEventCreate, CalendarEventUpdate, QueryCalendarParams


def reset_draft_from_main() -> int:
    """Reset draft calendar from main calendar and mark it clean.

    Returns:
        Number of events copied from main calendar into draft.

    Raises:
        ValueError: If main calendar is not initialized.
    """
    main_calendar = get_calendar()
    if main_calendar is None:
        raise ValueError("Main calendar is not initialized")

    draft_calendar = get_draft_calendar()
    if draft_calendar is None:
        draft_calendar = DraftCalendar()

    cloned_events = [event.model_copy(deep=True) for event in main_calendar.events]
    draft_calendar.update_events(cloned_events)
    draft_calendar.dirty = DirtyType.CLEAR
    set_draft_calendar(draft_calendar)
    return len(cloned_events)


def event_overlaps(left: CalendarEvent, right: CalendarEvent) -> bool:
    """Return True when two events overlap in time."""
    left_end = left.computed_end_time or left.deadline
    right_end = right.computed_end_time or right.deadline
    return left.scheduled_start < right_end and left_end > right.scheduled_start


def find_solid_conflicts(
    candidate: CalendarEvent,
    events: List[CalendarEvent],
    ignore_event_id: Optional[str] = None,
) -> List[CalendarEvent]:
    """Find all SOLID events that overlap with candidate event."""
    conflicts: List[CalendarEvent] = []
    for event in events:
        if ignore_event_id and event.id == ignore_event_id:
            continue
        if event.category != EventCategory.SOLID:
            continue
        if event_overlaps(candidate, event):
            conflicts.append(event)
    return conflicts


def summarize_events(events: List[CalendarEvent], sample_size: int = 5) -> Dict[str, Any]:
    """Build a compact summary payload for event results."""
    total = len(events)
    by_category: Dict[str, int] = {}
    for event in events:
        key = event.category.value
        by_category[key] = by_category.get(key, 0) + 1

    sorted_events = sorted(events, key=lambda item: item.scheduled_start)
    earliest = sorted_events[0].scheduled_start.isoformat() if sorted_events else None
    latest = (sorted_events[-1].computed_end_time or sorted_events[-1].deadline).isoformat() if sorted_events else None

    sample = []
    for event in sorted_events[:sample_size]:
        sample.append(
            {
                "id": event.id,
                "title": event.title,
                "scheduled_start": event.scheduled_start.isoformat(),
                "deadline": event.deadline.isoformat(),
                "duration": event.duration,
                "computed_end_time": (event.computed_end_time.isoformat() if event.computed_end_time else None),
                "category": event.category.value,
            }
        )

    return {
        "total": total,
        "by_category": by_category,
        "earliest_scheduled_start_time": earliest,
        "latest_computed_end_time": latest,
        "sample": sample,
    }


def build_event_from_create_model(event_create: CalendarEventCreate, fallback_id: Optional[str] = None) -> CalendarEvent:
    """Build CalendarEvent from CalendarEventCreate Pydantic model.

    Args:
        event_create: CalendarEventCreate model instance with validated event data.
        fallback_id: Optional fallback ID to use instead of auto-generated one.

    Returns:
        CalendarEvent instance built from the create model.

    Note:
        This function directly uses Pydantic model fields without additional
        parsing or validation, as Pydantic has already handled type conversion
        and validation.
    """
    event_data: Dict[str, Any] = {
        "title": event_create.title,
        "source": event_create.source,
        "scheduled_start": event_create.scheduled_start,
        "deadline": event_create.deadline,
        "duration": event_create.duration,
        "description": event_create.description,
        "priority": event_create.priority,
        "status": event_create.status,
        "category": event_create.category,
        "location": event_create.location,
        "tags": event_create.tags or [],
        "metadata": event_create.metadata or {},
    }

    if fallback_id is not None:
        event_data["id"] = fallback_id

    return CalendarEvent(**event_data)


def apply_event_updates(event: CalendarEvent, updates: CalendarEventUpdate) -> CalendarEvent:
    """Apply updates from CalendarEventUpdate model to an existing CalendarEvent.

    Args:
        event: Existing CalendarEvent instance to update.
        updates: CalendarEventUpdate model containing update values.
                 Only non-None fields will be applied.

    Returns:
        The updated CalendarEvent instance.

    Note:
        This function performs conditional updates - only fields with non-None
        values in the updates model will be modified on the event.
        The event is modified in place and returned.
    """
    if updates.title is not None:
        event.title = updates.title
    if updates.description is not None:
        event.description = updates.description
    if updates.source is not None:
        event.source = updates.source
    if updates.scheduled_start is not None:
        event.scheduled_start = updates.scheduled_start
    if updates.deadline is not None:
        event.deadline = updates.deadline
    if updates.duration is not None:
        event.duration = updates.duration
    if updates.priority is not None:
        event.priority = updates.priority
    if updates.status is not None:
        event.status = updates.status
    if updates.category is not None:
        event.category = updates.category
    if updates.location is not None:
        event.location = updates.location
    if updates.tags is not None:
        event.tags = updates.tags
    if updates.metadata is not None:
        event.metadata = updates.metadata

    event.updated_at = datetime.now()
    return event


# def build_event_from_payload(event_payload: Dict[str, Any], fallback_id: Optional[str] = None) -> CalendarEvent:
#     """Build CalendarEvent from payload with explicit parsing and validation.

#     .. deprecated::
#         This function is deprecated. Use `build_event_from_create_model` instead,
#         which accepts a CalendarEventCreate Pydantic model and provides better
#         type safety and validation.

#     Args:
#         event_payload: Dictionary containing event data.
#         fallback_id: Optional fallback ID to use instead of auto-generated one.

#     Returns:
#         CalendarEvent instance built from the payload.

#     Raises:
#         ValueError: If required fields are missing or invalid.
#     """
#     warnings.warn(
#         "build_event_from_payload is deprecated. Use build_event_from_create_model instead.",
#         DeprecationWarning,
#         stacklevel=2
#     )

#     if not isinstance(event_payload, dict):
#         raise ValueError("event must be an object")

#     event_data: Dict[str, Any] = dict(event_payload)
#     if fallback_id is not None:
#         event_data["id"] = fallback_id

#     required_fields = ["title", "source", "start_time", "end_time"]
#     missing_fields = [name for name in required_fields if name not in event_data]
#     if missing_fields:
#         raise ValueError(f"event is missing required fields: {', '.join(missing_fields)}")

#     if isinstance(event_data["start_time"], str):
#         event_data["start_time"] = datetime.fromisoformat(event_data["start_time"])
#     if isinstance(event_data["end_time"], str):
#         event_data["end_time"] = datetime.fromisoformat(event_data["end_time"])

#     if isinstance(event_data.get("source"), str):
#         event_data["source"] = EventSource(event_data["source"])

#     if event_data.get("priority") is not None and isinstance(event_data["priority"], str):
#         event_data["priority"] = Priority(event_data["priority"])
#     if event_data.get("status") is not None and isinstance(event_data["status"], str):
#         event_data["status"] = EventStatus(event_data["status"])
#     if event_data.get("category") is not None and isinstance(event_data["category"], str):
#         event_data["category"] = EventCategory(event_data["category"])

#     return CalendarEvent(**event_data)


def serialize_event(event: CalendarEvent) -> Dict[str, Any]:
    """Serialize event into a JSON-friendly dict."""
    return {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "source": event.source.value,
        "scheduled_start": event.scheduled_start.isoformat(),
        "deadline": event.deadline.isoformat(),
        "duration": event.duration,
        "computed_end_time": event.computed_end_time.isoformat() if event.computed_end_time else None,
        "priority": event.priority.value if event.priority else None,
        "status": event.status.value if event.status else None,
        "category": event.category.value,
        "location": event.location,
        "tags": event.tags,
        "metadata": event.metadata,
    }


def apply_query_filters(events: List[CalendarEvent], params: QueryCalendarParams) -> List[CalendarEvent]:
    """Filter events by optional query conditions using QueryCalendarParams.

    Args:
        events: List of CalendarEvent instances to filter.
        params: QueryCalendarParams model containing filter conditions.
                Only non-None fields will be used for filtering.

    Returns:
        Filtered and sorted list of CalendarEvent instances.

    Note:
        This function uses Pydantic model fields directly, eliminating the need
        for manual type parsing and validation.
    """
    def _is_aware(dt: datetime) -> bool:
        return dt.tzinfo is not None and dt.utcoffset() is not None

    def _normalize_pair(left: datetime, right: datetime) -> tuple[datetime, datetime]:
        if _is_aware(left):
            target_tz = left.tzinfo
        elif _is_aware(right):
            target_tz = right.tzinfo
        else:
            target_tz = datetime.now().astimezone().tzinfo

        if _is_aware(left):
            left_cmp = left.astimezone(target_tz)
        else:
            left_cmp = left.replace(tzinfo=target_tz)

        if _is_aware(right):
            right_cmp = right.astimezone(target_tz)
        else:
            right_cmp = right.replace(tzinfo=target_tz)

        return left_cmp, right_cmp

    def _gte(left: datetime, right: datetime) -> bool:
        left_cmp, right_cmp = _normalize_pair(left, right)
        return left_cmp >= right_cmp

    def _lte(left: datetime, right: datetime) -> bool:
        left_cmp, right_cmp = _normalize_pair(left, right)
        return left_cmp <= right_cmp

    def _sort_key(dt: datetime) -> float:
        if _is_aware(dt):
            return dt.timestamp()
        local_tz = datetime.now().astimezone().tzinfo
        return dt.replace(tzinfo=local_tz).timestamp()

    filtered = list(events)

    if params.start_time is not None:
        filtered = [event for event in filtered if _gte(event.deadline, params.start_time)]
    if params.end_time is not None:
        filtered = [event for event in filtered if _lte(event.scheduled_start, params.end_time)]
    if params.event_id is not None:
        filtered = [event for event in filtered if event.id == params.event_id]
    if params.source is not None:
        filtered = [event for event in filtered if event.source == params.source]
    if params.category is not None:
        filtered = [event for event in filtered if event.category == params.category]
    if params.status is not None:
        filtered = [event for event in filtered if event.status == params.status]
    if params.title_keyword:
        keyword = str(params.title_keyword).strip().lower()
        filtered = [event for event in filtered if keyword in event.title.lower()]

    return sorted(filtered, key=lambda event: _sort_key(event.scheduled_start))


def format_conflict_message(conflicts: List[CalendarEvent]) -> str:
    """Build readable error message for overlap conflicts."""
    details = []
    for event in conflicts:
        details.append(
            f"id={event.id}, title={event.title}, "
            f"scheduled_start={event.scheduled_start.isoformat()}, deadline={event.deadline.isoformat()}"
        )
    return "Time conflict with SOLID events: " + "; ".join(details)
