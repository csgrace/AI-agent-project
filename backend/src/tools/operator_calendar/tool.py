"""Calendar tools for editing draft calendar events."""

import json
from typing import Any, Dict, List

from langchain.tools import tool

from ...core.global_state import get_calendar, get_draft_calendar
from ...models.calendar.calendar_event import CalendarEvent
from ...models.calendar.enums import DirtyType
from .utils import (
    apply_event_updates,
    apply_query_filters,
    build_event_from_create_model,
    find_solid_conflicts,
    format_conflict_message,
    reset_draft_from_main,
    serialize_event,
    summarize_events,
)
from .schemas import (
    QueryCalendarParams,
    AddCalendarEventParams,
    RemoveCalendarEventParams,
    UpdateCalendarEventParams,
)


def _require_draft_calendar():
    draft_calendar = get_draft_calendar()
    if draft_calendar is None:
        raise ValueError("Draft calendar is not initialized")
    return draft_calendar


def _require_editable_draft_calendar():
    draft_calendar = _require_draft_calendar()
    # Check if there are uncommitted fetched events
    if draft_calendar.dirty == DirtyType.FETCH:
        raise ValueError(
            "There are uncommitted fetched events in the draft calendar. "
            "Please commit or reset draft before making modifications."
        )
    return draft_calendar


def _require_main_calendar():
    main_calendar = get_calendar()
    if main_calendar is None:
        raise ValueError("Main calendar is not initialized")
    return main_calendar


@tool
def query_calendar(params: QueryCalendarParams) -> str:
    """Query events in selected calendar.

    Args:
        params: Query parameters including filters, return options, and source selector.

    Returns:
        JSON string containing query result. When result size exceeds max_inline,
        returns summary plus guidance to raise max_inline or narrow filters.

    Raises:
        ValueError: If selected calendar is not initialized.
    """
    if params.use_main_calendar:
        calendar_events = _require_main_calendar().events
    else:
        calendar_events = _require_draft_calendar().events

    filtered_events = apply_query_filters(calendar_events, params)
    
    summary = summarize_events(filtered_events)
    result: Dict[str, Any] = {
        "ok": True,
        "action": "query",
        "summary": summary,
    }

    if params.detail_level == "full" and len(filtered_events) <= params.max_inline:
        result["events"] = [serialize_event(event) for event in filtered_events]
    elif len(filtered_events) <= params.max_inline:
        result["events"] = [serialize_event(event) for event in filtered_events]
    else:
        result["overflow"] = True
        result["max_inline"] = params.max_inline
        result["recommended_max_inline"] = len(filtered_events)
        result["message"] = (
            "Result set exceeds max_inline. Increase max_inline or narrow query filters."
        )

    return json.dumps(result, ensure_ascii=False)


@tool

def add_calendar_event(params: AddCalendarEventParams) -> str:
    """Add one event to draft calendar.

    Args:
        params: Event information to add.

    Returns:
        JSON string containing the added event and operation status.

    Raises:
        ValueError: If draft calendar is not initialized or conflict is detected.
    """
    draft_calendar = _require_editable_draft_calendar()
    
    candidate = build_event_from_create_model(params.event)

    conflicts = find_solid_conflicts(candidate, draft_calendar.events)
    if conflicts:
        raise ValueError(format_conflict_message(conflicts))

    draft_calendar.add_event(candidate)
    draft_calendar.dirty = DirtyType.MODIFY
    result = {
        "ok": True,
        "action": "add",
        "event": serialize_event(candidate),
        "dirty": draft_calendar.dirty,
    }
    return json.dumps(result, ensure_ascii=False)


@tool

def remove_calendar_event(params: RemoveCalendarEventParams) -> str:
    """Remove one event from draft calendar by id.

    Args:
        params: Event ID to remove.

    Returns:
        JSON string containing operation status and removed event ID.

    Raises:
        ValueError: If draft calendar is not initialized.
    """
    draft_calendar = _require_editable_draft_calendar()
    
    removed = draft_calendar.remove_event(params.event_id)
    if removed:
        draft_calendar.dirty = DirtyType.MODIFY
    result = {
        "ok": True,
        "action": "remove",
        "event_id": params.event_id,
        "removed": removed,
        "dirty": draft_calendar.dirty,
    }
    return json.dumps(result, ensure_ascii=False)


@tool

def update_calendar_event(params: UpdateCalendarEventParams) -> str:
    """Update one event in draft calendar by id.

    Args:
        params: Event ID and update information.

    Returns:
        JSON string containing the updated event and operation status.

    Raises:
        ValueError: If draft calendar is not initialized, event not found, or conflict is detected.
    """
    draft_calendar = _require_editable_draft_calendar()
    
    existing = draft_calendar.get_event(params.event_id)
    if existing is None:
        raise ValueError(f"event not found: {params.event_id}")

    apply_event_updates(existing, params.updates)

    conflicts = find_solid_conflicts(existing, draft_calendar.events, ignore_event_id=existing.id)
    if conflicts:
        raise ValueError(format_conflict_message(conflicts))

    draft_calendar.dirty = DirtyType.MODIFY

    result = {
        "ok": True,
        "action": "update",
        "event": serialize_event(existing),
        "dirty": draft_calendar.dirty,
    }
    return json.dumps(result, ensure_ascii=False)


@tool
def clear_draft_calendar() -> str:
    """Clear all events from draft calendar.

    Returns:
        JSON string containing operation status and number of cleared events.

    Raises:
        ValueError: If draft calendar is not initialized.
    """
    draft_calendar = _require_editable_draft_calendar()
    
    cleared_count = len(draft_calendar.events)
    draft_calendar.clear_events()
    draft_calendar.dirty = DirtyType.MODIFY
    
    result = {
        "ok": True,
        "action": "clear",
        "cleared_count": cleared_count,
        "dirty": draft_calendar.dirty,
    }
    return json.dumps(result, ensure_ascii=False)


@tool
def reset_draft() -> str:
    """Reset draft calendar from main calendar and mark draft as clean.

    Returns:
        JSON string containing operation status and copied event count.

    Raises:
        ValueError: If main calendar is not initialized.
    """
    copied_count = reset_draft_from_main()
    result = {
        "ok": True,
        "action": "reset",
        "reset_count": copied_count,
        "dirty": DirtyType.CLEAR,
    }
    return json.dumps(result, ensure_ascii=False)
