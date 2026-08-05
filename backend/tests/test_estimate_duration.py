"""Unit tests for estimate_duration tool."""
from datetime import datetime, timedelta
from unittest.mock import patch
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.global_state import get_object_store, set_object_store
from src.core.object_store import ObjectStore
from src.models.calendar.calendar_event import CalendarEvent
from src.models.calendar.enums import EventSource
from src.tools.estimate_duration.tool import estimate_event_durations_from_store


@pytest.fixture(autouse=True)
def clean_object_store():
    """Reset global ObjectStore before each test."""
    set_object_store(ObjectStore())
    yield
    set_object_store(ObjectStore())


def _build_event(title: str, hours: int = 1, duration_minutes=None) -> CalendarEvent:
    start = datetime.now()
    return CalendarEvent(
        title=title,
        scheduled_start=start,
        deadline=start + timedelta(hours=hours),
        source=EventSource.UNIVERSITY,
        duration=duration_minutes,
    )


class TestEstimateDurationTool:
    def test_key_in_key_out_and_only_fill_missing(self):
        store = get_object_store()
        event_missing = _build_event("Research Task", duration_minutes=None)
        event_existing = _build_event("Preset Event", duration_minutes=30)

        input_key = store.put([event_missing, event_existing], metadata={"kind": "calendar_event_list"})

        with patch("src.tools.estimate_duration.utils._estimate_minutes_with_llm", return_value=75):
            output_key = estimate_event_durations_from_store.invoke({
                "object_store_key": input_key,
                "user_hint": "prefer realistic study duration",
                "missing_only": True,
            })

        assert output_key != input_key
        result_events = store.get(output_key)
        assert len(result_events) == 2

        assert result_events[0].duration == 75
        assert result_events[1].duration == 30

        output_metadata = store.get_metadata(output_key)
        assert output_metadata["source_key"] == input_key
        assert output_metadata["generated_by"] == "estimate_event_durations_from_store"

    def test_missing_only_false_overwrites_existing_duration(self):
        store = get_object_store()
        event = _build_event("Team Meeting", duration_minutes=30)
        input_key = store.put([event])

        with patch("src.tools.estimate_duration.utils._estimate_minutes_with_llm", return_value=30):
            output_key = estimate_event_durations_from_store.invoke({
                "object_store_key": input_key,
                "missing_only": False,
            })

        result_events = store.get(output_key)
        assert result_events[0].duration == 30

    def test_invalid_input_key_raises(self):
        with pytest.raises(KeyError):
            estimate_event_durations_from_store.invoke({"object_store_key": "missing_key"})

    def test_invalid_object_type_raises(self):
        store = get_object_store()
        bad_key = store.put({"not": "event list"})

        with pytest.raises(TypeError):
            estimate_event_durations_from_store.invoke({"object_store_key": bad_key})

    def test_memory_disabled_constant_bypasses_memory_query(self):
        store = get_object_store()
        event_missing = _build_event("Research Task", duration_minutes=None)
        input_key = store.put([event_missing], metadata={"kind": "calendar_event_list"})

        with patch("src.tools.estimate_duration.utils.ENABLE_MEMORY_CONTEXT", False):
            with patch("src.tools.estimate_duration.utils.MemoryAdapter.query_context", side_effect=AssertionError("memory should be bypassed")):
                with patch("src.tools.estimate_duration.utils._estimate_minutes_with_llm", return_value=40):
                    output_key = estimate_event_durations_from_store.invoke({
                        "object_store_key": input_key,
                    })

        result_events = store.get(output_key)
        assert result_events[0].duration == 40
