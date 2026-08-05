"""Unit tests for ObjectStore."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.object_store import ObjectStore
from src.models.calendar.calendar_event import CalendarEvent
from src.models.calendar.enums import EventSource
from datetime import datetime, timedelta


class TestObjectStore:
    """Test ObjectStore core behaviors."""

    def test_put_get_roundtrip(self):
        store = ObjectStore()
        key = store.put({"items": [1, 2, 3]})

        value = store.get(key)
        assert value == {"items": [1, 2, 3]}

    def test_get_returns_deep_copy(self):
        store = ObjectStore()
        key = store.put({"items": [1, 2, 3]})

        value = store.get(key)
        value["items"].append(4)

        fresh_value = store.get(key)
        assert fresh_value == {"items": [1, 2, 3]}

    def test_clone_creates_new_key_and_metadata(self):
        store = ObjectStore()
        key = store.put([1, 2], metadata={"kind": "list"})

        cloned_key = store.clone(key, metadata={"stage": "estimated"})
        assert cloned_key != key
        assert store.get(cloned_key) == [1, 2]

        metadata = store.get_metadata(cloned_key)
        assert metadata["cloned_from"] == key
        assert metadata["kind"] == "list"
        assert metadata["stage"] == "estimated"

    def test_get_with_expected_type_mismatch(self):
        store = ObjectStore()
        key = store.put([1, 2, 3])

        try:
            store.get(key, expected_type=dict)
            assert False, "Expected TypeError"
        except TypeError:
            assert True

    def test_missing_key_raises_key_error(self):
        store = ObjectStore()
        try:
            store.get("missing-key")
            assert False, "Expected KeyError"
        except KeyError:
            assert True

    def test_get_typed_validates_list_item_type(self):
        store = ObjectStore()
        event = CalendarEvent(
            title="Test",
            scheduled_start=datetime.now(),
            deadline=datetime.now() + timedelta(hours=1),
            source=EventSource.UNIVERSITY,
        )
        key = store.put([event])

        value = store.get_typed(key, list[CalendarEvent])
        assert len(value) == 1
        assert isinstance(value[0], CalendarEvent)

    def test_get_typed_raises_on_invalid_item_type(self):
        store = ObjectStore()
        key = store.put(["not-event"])

        with pytest.raises(TypeError):
            store.get_typed(key, list[CalendarEvent])
