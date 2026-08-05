"""Tests for object_store_reader tool."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.global_state import get_object_store, set_object_store
from src.core.object_store import ObjectStore
from src.tools.object_store_reader.tool import read_object_store_item


@pytest.fixture(autouse=True)
def reset_store():
    set_object_store(ObjectStore())
    yield
    set_object_store(ObjectStore())


def test_read_object_store_item_success():
    key = get_object_store().put(
        [{"title": "任务A"}, {"title": "任务B"}],
        metadata={"kind": "calendar_event_list", "generated_by": "unit_test"},
    )

    raw = read_object_store_item.invoke({"object_store_key": key})
    result = json.loads(raw)

    assert result["ok"] is True
    assert result["action"] == "read_object_store_item"
    assert result["object_store_key"] == key
    assert result["value_type"] == "list"
    assert result["metadata"]["generated_by"] == "unit_test"
    assert result["value"][0]["title"] == "任务A"


def test_read_object_store_item_missing_key_raises():
    with pytest.raises(ValueError, match="ObjectStore key not found"):
        read_object_store_item.invoke({"object_store_key": "obj_not_exists"})
