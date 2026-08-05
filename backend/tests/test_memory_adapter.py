"""Unit tests for memory adapter behavior."""
from datetime import datetime, timedelta
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.calendar.calendar_event import CalendarEvent
from src.models.calendar.enums import EventSource
from src.tools.shared_utils.memory_adapter import MemoryAdapter


class WorkingProvider:
    def query_context(self, event, top_k=3):
        return [{"hint": "usually 60 minutes"}]


class BrokenProvider:
    def query_context(self, event, top_k=3):
        raise RuntimeError("memory backend unavailable")


def _build_event() -> CalendarEvent:
    now = datetime.now()
    return CalendarEvent(
        title="Team Meeting",
        scheduled_start=now,
        deadline=now + timedelta(hours=1),
        source=EventSource.UNIVERSITY,
    )


class TestMemoryAdapter:
    def test_query_context_success(self):
        adapter = MemoryAdapter(provider=WorkingProvider())
        event = _build_event()

        result = adapter.query_context(event=event, top_k=2)
        assert result == [{"hint": "usually 60 minutes"}]

    def test_query_context_fallback_on_error(self):
        adapter = MemoryAdapter(provider=BrokenProvider())
        event = _build_event()

        result = adapter.query_context(event=event, top_k=2)
        assert result == []
