from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException

from ...core.global_state import get_calendar, get_draft_calendar
from ...models.calendar.enums import (
    DirtyType,
    EventSource,
    Priority,
    EventStatus,
    EventCategory,
)
from ...models.calendar.calendar_event import CalendarEvent
from ...services.init_calendar.loader import save_calendar_to_file
from ...tools.operator_calendar.utils import (
    build_event_from_create_model,
    reset_draft_from_main,
    find_solid_conflicts,
    format_conflict_message,
)
from ...tools.operator_calendar.schemas import (
    CalendarEventCreate,
    CalendarEventUpdate,
)
from ..schemas import (
    CalendarResponse,
    DraftCalendarResponse,
    CreateEventRequest,
    UpdateEventRequest,
    CommitResponse,
    ResetDraftResponse,
    CalendarDiffResponse,
)
from ..converters import calendar_to_response, draft_to_response

from pathlib import Path

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

CALENDAR_PERSIST_PATH = Path(__file__).resolve().parents[3] /"data"/"tis_download"/"calendar.json"

@router.get("", response_model=CalendarResponse)
def get_main_calendar():
    calendar = get_calendar()
    if calendar is None:
        raise HTTPException(status_code=404, detail="Calendar not initialized")
    return calendar_to_response(calendar)


@router.get("/draft", response_model=DraftCalendarResponse)
def get_draft():
    draft = get_draft_calendar()
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft calendar not initialized")
    return draft_to_response(draft)


@router.post("/events", response_model=DraftCalendarResponse)
def add_event(req: CreateEventRequest):
    draft = get_draft_calendar()
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft calendar not initialized")

    if draft.dirty == DirtyType.FETCH:
        raise HTTPException(
            status_code=409,
            detail="There are uncommitted fetched events. Commit or reset first.",
        )

    try:
        scheduled_start = datetime.fromisoformat(req.scheduled_start)
        deadline = datetime.fromisoformat(req.deadline)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Invalid datetime format: {e}")

    try:
        source = EventSource(req.source)
    except ValueError:
        source = EventSource.PERSONAL

    create_model = CalendarEventCreate(
        title=req.title,
        source=source,
        scheduled_start=scheduled_start,
        deadline=deadline,
        duration=req.duration,
        description=req.description,
        priority=Priority(req.priority) if req.priority else None,
        status=EventStatus(req.status) if req.status else None,
        category=EventCategory(req.category) if req.category else EventCategory.SCHEDULABLE,
        location=req.location,
        tags=req.tags,
        metadata=req.metadata,
    )

    candidate = build_event_from_create_model(create_model)

    conflicts = find_solid_conflicts(candidate, draft.events)
    if conflicts:
        raise HTTPException(status_code=409, detail=format_conflict_message(conflicts))

    candidate.color_tag = req.color_tag
    draft.add_event(candidate)
    draft.dirty = DirtyType.MODIFY

    return draft_to_response(draft)


@router.put("/events/{event_id}", response_model=DraftCalendarResponse)
def update_event(event_id: str, req: UpdateEventRequest):
    draft = get_draft_calendar()
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft calendar not initialized")

    if draft.dirty == DirtyType.FETCH:
        raise HTTPException(
            status_code=409,
            detail="There are uncommitted fetched events. Commit or reset first.",
        )

    existing = draft.get_event(event_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Event not found: {event_id}")

    update_data = {}
    if req.title is not None:
        update_data["title"] = req.title
    if req.description is not None:
        update_data["description"] = req.description
    if req.source is not None:
        try:
            update_data["source"] = EventSource(req.source)
        except ValueError:
            pass
    if req.scheduled_start is not None:
        try:
            update_data["scheduled_start"] = datetime.fromisoformat(req.scheduled_start)
        except ValueError:
            pass
    if req.deadline is not None:
        try:
            update_data["deadline"] = datetime.fromisoformat(req.deadline)
        except ValueError:
            pass
    if req.duration is not None:
        update_data["duration"] = req.duration
    if req.location is not None:
        update_data["location"] = req.location
    if req.priority is not None:
        try:
            update_data["priority"] = Priority(req.priority)
        except ValueError:
            pass
    if req.status is not None:
        try:
            update_data["status"] = EventStatus(req.status)
        except ValueError:
            pass
    if req.category is not None:
        try:
            update_data["category"] = EventCategory(req.category)
        except ValueError:
            pass
    if req.color_tag is not None:
        existing.color_tag = req.color_tag
    if req.tags is not None:
        update_data["tags"] = req.tags
    if req.metadata is not None:
        update_data["metadata"] = req.metadata

    if update_data:
        update_model = CalendarEventUpdate(**update_data)
        from ...tools.operator_calendar.utils import apply_event_updates
        apply_event_updates(existing, update_model)

    conflicts = find_solid_conflicts(existing, draft.events, ignore_event_id=existing.id)
    if conflicts:
        raise HTTPException(status_code=409, detail=format_conflict_message(conflicts))

    draft.dirty = DirtyType.MODIFY

    return draft_to_response(draft)


@router.delete("/events/{event_id}", response_model=DraftCalendarResponse)
def remove_event(event_id: str):
    draft = get_draft_calendar()
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft calendar not initialized")

    if draft.dirty == DirtyType.FETCH:
        raise HTTPException(
            status_code=409,
            detail="There are uncommitted fetched events. Commit or reset first.",
        )

    removed = draft.remove_event(event_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Event not found: {event_id}")

    draft.dirty = DirtyType.MODIFY

    return draft_to_response(draft)


@router.post("/commit", response_model=CommitResponse)
def commit_draft():
    calendar = get_calendar()
    draft = get_draft_calendar()
    if calendar is None:
        raise HTTPException(status_code=404, detail="Calendar not initialized")
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft calendar not initialized")

    synced_count = calendar.sync_draft(draft, partial_update=False)
    draft.dirty = DirtyType.CLEAR
    save_calendar_to_file(calendar, CALENDAR_PERSIST_PATH)

    return CommitResponse(ok=True, synced_count=synced_count)


@router.post("/reset-draft", response_model=ResetDraftResponse)
def reset_draft():
    try:
        reset_count = reset_draft_from_main()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return ResetDraftResponse(ok=True, reset_count=reset_count)


@router.get("/diff", response_model=CalendarDiffResponse)
def get_calendar_diff():
    """Get the difference between main calendar and draft calendar."""
    calendar = get_calendar()
    draft = get_draft_calendar()
    if calendar is None:
        raise HTTPException(status_code=404, detail="Calendar not initialized")
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft calendar not initialized")

    # Create event ID maps for quick lookup
    main_events_by_id = {event.id: event for event in calendar.events}
    draft_events_by_id = {event.id: event for event in draft.events}

    # Find new events (in draft but not in main)
    new_events = []
    # Find modified events (in both, but different)
    modified_events = []
    # Find deleted events (in main but not in draft)
    deleted_events = []

    # Check draft events
    for event_id, draft_event in draft_events_by_id.items():
        if event_id not in main_events_by_id:
            # New event
            new_events.append(draft_event)
        else:
            # Check if modified
            main_event = main_events_by_id[event_id]
            # Compare relevant fields
            if (
                draft_event.title != main_event.title or
                draft_event.description != main_event.description or
                draft_event.scheduled_start != main_event.scheduled_start or
                draft_event.deadline != main_event.deadline or
                draft_event.location != main_event.location
            ):
                modified_events.append({
                    "main": main_event,
                    "draft": draft_event
                })

    # Check deleted events
    for event_id, main_event in main_events_by_id.items():
        if event_id not in draft_events_by_id:
            deleted_events.append(main_event)

    return CalendarDiffResponse(
        new_events=[event.model_dump() for event in new_events],
        modified_events=[{
            "main": event["main"].model_dump(),
            "draft": event["draft"].model_dump()
        } for event in modified_events],
        deleted_events=[event.model_dump() for event in deleted_events]
    )
