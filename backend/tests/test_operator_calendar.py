"""Tests for operator_calendar tool."""

import json
import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.global_state import set_calendar, set_draft_calendar, set_object_store, get_draft_calendar
from src.core.object_store import ObjectStore
from src.models.calendar.calendar import Calendar
from src.models.calendar.calendar_event import CalendarEvent
from src.models.calendar.draft_calendar import DraftCalendar
from src.models.calendar.enums import DirtyType, EventCategory, EventSource, EventStatus, Priority
from src.tools.operator_calendar.tool import (
    query_calendar,
    add_calendar_event,
    remove_calendar_event,
    update_calendar_event,
    clear_draft_calendar,
    reset_draft,
)
from src.tools.operator_calendar.schemas import (
    QueryCalendarParams,
    AddCalendarEventParams,
    RemoveCalendarEventParams,
    UpdateCalendarEventParams,
    CalendarEventCreate,
    CalendarEventUpdate,
)


@pytest.fixture(autouse=True)
def reset_state():
    set_object_store(ObjectStore())
    set_calendar(None)
    set_draft_calendar(None)
    yield
    set_object_store(ObjectStore())
    set_calendar(None)
    set_draft_calendar(None)


def _make_event(title: str, start_offset_hours: int, end_offset_hours: int, category: EventCategory) -> CalendarEvent:
    base = datetime(2026, 4, 16, 8, 0, 0)
    duration_minutes = (end_offset_hours - start_offset_hours) * 60
    return CalendarEvent(
        title=title,
        source=EventSource.PERSONAL,
        scheduled_start=base + timedelta(hours=start_offset_hours),
        deadline=base + timedelta(hours=end_offset_hours),
        duration=duration_minutes,
        category=category,
        status=EventStatus.PENDING,
        priority=Priority.MEDIUM,
    )


class TestOperatorCalendar:
    def test_query_params_normalize_aware_to_cn_naive(self):
        params = QueryCalendarParams(
            start_time=datetime.fromisoformat("2026-05-01T00:00:00+00:00"),
            end_time=datetime.fromisoformat("2026-05-01T12:00:00+00:00"),
        )

        assert params.start_time is not None
        assert params.end_time is not None
        assert params.start_time.tzinfo is None
        assert params.end_time.tzinfo is None
        assert params.start_time.hour == 8
        assert params.end_time.hour == 20

    def test_create_params_normalize_aware_to_cn_naive(self):
        event_create = CalendarEventCreate(
            title="Aware Input",
            source=EventSource.PERSONAL,
            scheduled_start=datetime.fromisoformat("2026-04-18T10:00:00+00:00"),
            deadline=datetime.fromisoformat("2026-04-18T12:00:00+00:00"),
            duration=120,
            category=EventCategory.SCHEDULABLE,
            status=EventStatus.PENDING,
            priority=Priority.MEDIUM,
        )

        assert event_create.scheduled_start.tzinfo is None
        assert event_create.deadline.tzinfo is None
        assert event_create.scheduled_start.hour == 18
        assert event_create.deadline.hour == 20

    def test_add_event_success(self):
        draft = DraftCalendar()
        solid = _make_event("Fixed Class", 1, 2, EventCategory.SOLID)
        draft.add_event(solid)
        set_draft_calendar(draft)

        event_create = CalendarEventCreate(
            title="Study Session",
            source=EventSource.PERSONAL,
            scheduled_start=datetime(2026, 4, 16, 11, 0, 0),
            deadline=datetime(2026, 4, 16, 12, 0, 0),
            duration=60,
            category=EventCategory.SCHEDULABLE,
            status=EventStatus.PENDING,
            priority=Priority.MEDIUM,
        )
        params = AddCalendarEventParams(event=event_create)
        raw = add_calendar_event.invoke({"params": params.model_dump()})
        result = json.loads(raw)

        assert result["ok"] is True
        assert result["action"] == "add"
        assert get_draft_calendar() is not None
        assert len(get_draft_calendar().events) == 2

    def test_add_event_accepts_natural_duration_and_string_enums(self):
        draft = DraftCalendar()
        set_draft_calendar(draft)

        raw = add_calendar_event.invoke(
            {
                "params": {
                    "event": {
                        "title": "Hiking",
                        "source": "PERSONAL",
                        "scheduled_start": "2026-04-19T15:00:00+08:00",
                        "deadline": "2026-04-19T18:00:00+08:00",
                        "duration": "about 3 hours",
                        "category": "SCHEDULABLE",
                        "status": "PENDING",
                        "priority": "MEDIUM",
                    }
                }
            }
        )
        result = json.loads(raw)

        assert result["ok"] is True
        assert result["event"]["duration"] == 180
        assert result["event"]["source"] == "personal"

    def test_add_event_conflict_with_solid_raises(self):
        draft = DraftCalendar()
        draft.add_event(_make_event("Fixed Class", 1, 3, EventCategory.SOLID))
        set_draft_calendar(draft)

        event_create = CalendarEventCreate(
            title="Overlapping Task",
            source=EventSource.PERSONAL,
            scheduled_start=datetime(2026, 4, 16, 10, 30, 0),
            deadline=datetime(2026, 4, 16, 11, 30, 0),
            duration=60,
            category=EventCategory.SCHEDULABLE,
            status=EventStatus.PENDING,
            priority=Priority.MEDIUM,
        )
        params = AddCalendarEventParams(event=event_create)

        with pytest.raises(ValueError, match="Time conflict with SOLID events"):
            add_calendar_event.invoke({"params": params.model_dump()})

    def test_update_event_conflict_raises(self):
        draft = DraftCalendar()
        solid = _make_event("Fixed Class", 1, 3, EventCategory.SOLID)
        movable = _make_event("Task", 4, 5, EventCategory.SCHEDULABLE)
        draft.add_event(solid)
        draft.add_event(movable)
        set_draft_calendar(draft)

        event_update = CalendarEventUpdate(
            scheduled_start=datetime(2026, 4, 16, 10, 30, 0),
            deadline=datetime(2026, 4, 16, 11, 30, 0),
        )
        params = UpdateCalendarEventParams(event_id=movable.id, updates=event_update)

        with pytest.raises(ValueError, match="Time conflict with SOLID events"):
            update_calendar_event.invoke({"params": params.model_dump()})

    def test_query_large_result_returns_overflow_guidance(self):
        draft = DraftCalendar()
        draft.add_event(_make_event("A", 1, 2, EventCategory.SCHEDULABLE))
        draft.add_event(_make_event("B", 3, 4, EventCategory.SCHEDULABLE))
        set_draft_calendar(draft)

        params = QueryCalendarParams(detail_level="summary", max_inline=1)
        raw = query_calendar.invoke({"params": params.model_dump()})
        result = json.loads(raw)

        assert result["ok"] is True
        assert result["action"] == "query"
        assert result["summary"]["total"] == 2
        assert result["overflow"] is True
        assert result["max_inline"] == 1
        assert result["recommended_max_inline"] == 2

    def test_query_uses_main_calendar_when_flag_true(self):
        main = Calendar(name="Main")
        main_event = _make_event("Main Event", 1, 2, EventCategory.SCHEDULABLE)
        main.add_event(main_event)
        set_calendar(main)

        draft = DraftCalendar()
        draft.add_event(_make_event("Draft Event", 3, 4, EventCategory.SCHEDULABLE))
        set_draft_calendar(draft)

        params = QueryCalendarParams(use_main_calendar=True, detail_level="full", max_inline=10)
        raw = query_calendar.invoke({"params": params.model_dump()})
        result = json.loads(raw)

        assert result["ok"] is True
        assert result["summary"]["total"] == 1
        assert result["events"][0]["title"] == "Main Event"

    def test_query_uses_draft_when_flag_false(self):
        main = Calendar(name="Main")
        main.add_event(_make_event("Main Event", 1, 2, EventCategory.SCHEDULABLE))
        set_calendar(main)

        draft = DraftCalendar()
        draft_event = _make_event("Draft Event", 3, 4, EventCategory.SCHEDULABLE)
        draft.add_event(draft_event)
        set_draft_calendar(draft)

        params = QueryCalendarParams(use_main_calendar=False, detail_level="full", max_inline=10)
        raw = query_calendar.invoke({"params": params.model_dump()})
        result = json.loads(raw)

        assert result["ok"] is True
        assert result["summary"]["total"] == 1
        assert result["events"][0]["title"] == "Draft Event"

    def test_query_handles_event_without_duration(self):
        draft = DraftCalendar()
        draft.add_event(
            CalendarEvent(
                title="No Duration",
                source=EventSource.PERSONAL,
                scheduled_start=datetime(2026, 4, 16, 9, 0, 0),
                deadline=datetime(2026, 4, 16, 10, 0, 0),
                duration=None,
                category=EventCategory.SCHEDULABLE,
                status=EventStatus.PENDING,
                priority=Priority.MEDIUM,
            )
        )
        set_draft_calendar(draft)

        params = QueryCalendarParams(detail_level="full", max_inline=10)
        raw = query_calendar.invoke({"params": params.model_dump()})
        result = json.loads(raw)

        assert result["ok"] is True
        assert result["summary"]["total"] == 1
        assert result["events"][0]["computed_end_time"] is None

    def test_query_handles_mixed_naive_and_aware_datetimes(self):
        draft = DraftCalendar()
        draft.add_event(
            CalendarEvent(
                title="Naive Event",
                source=EventSource.PERSONAL,
                scheduled_start=datetime(2026, 5, 10, 9, 0, 0),
                deadline=datetime(2026, 5, 10, 11, 0, 0),
                duration=120,
                category=EventCategory.SCHEDULABLE,
                status=EventStatus.PENDING,
                priority=Priority.MEDIUM,
            )
        )
        set_draft_calendar(draft)

        params = QueryCalendarParams(
            start_time=datetime.fromisoformat("2026-05-01T00:00:00+08:00"),
            end_time=datetime.fromisoformat("2026-05-31T23:59:59+08:00"),
            detail_level="full",
            max_inline=10,
        )
        raw = query_calendar.invoke({"params": params.model_dump()})
        result = json.loads(raw)

        assert result["ok"] is True
        assert result["summary"]["total"] == 1
        assert result["events"][0]["title"] == "Naive Event"

    def test_remove_event_success(self):
        draft = DraftCalendar()
        event = _make_event("Task", 1, 2, EventCategory.SCHEDULABLE)
        draft.add_event(event)
        set_draft_calendar(draft)

        params = RemoveCalendarEventParams(event_id=event.id)
        raw = remove_calendar_event.invoke({"params": params.model_dump()})
        result = json.loads(raw)

        assert result["ok"] is True
        assert result["removed"] is True
        assert len(get_draft_calendar().events) == 0

    def test_missing_draft_calendar_raises(self):
        params = QueryCalendarParams()
        with pytest.raises(ValueError, match="Draft calendar is not initialized"):
            query_calendar.invoke({"params": params.model_dump()})

    def test_clear_draft_marks_modify(self):
        draft = DraftCalendar()
        draft.add_event(_make_event("Task", 1, 2, EventCategory.SCHEDULABLE))
        set_draft_calendar(draft)

        raw = clear_draft_calendar.invoke({})
        result = json.loads(raw)

        assert result["ok"] is True
        assert result["action"] == "clear"
        assert result["cleared_count"] == 1
        assert result["dirty"] == DirtyType.MODIFY
        assert len(get_draft_calendar().events) == 0

    def test_reset_draft_restores_main_and_marks_clear(self):
        main = Calendar(name="Main")
        main.add_event(_make_event("Main Event", 1, 2, EventCategory.SCHEDULABLE))
        set_calendar(main)

        draft = DraftCalendar()
        draft.add_event(_make_event("Draft Event", 3, 4, EventCategory.SCHEDULABLE))
        draft.dirty = DirtyType.MODIFY
        set_draft_calendar(draft)

        raw = reset_draft.invoke({})
        result = json.loads(raw)

        assert result["ok"] is True
        assert result["action"] == "reset"
        assert result["dirty"] == DirtyType.CLEAR
        assert result["reset_count"] == 1

        restored = get_draft_calendar()
        assert restored is not None
        assert len(restored.events) == 1
        assert restored.events[0].title == "Main Event"
        assert restored.dirty == DirtyType.CLEAR
