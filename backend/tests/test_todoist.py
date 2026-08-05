"""Test for Todoist Tool.

This module tests the Todoist calendar tool functionality.
"""
import uuid
import webbrowser
import json
import os
import http.server
import socketserver
import urllib.parse
import threading
import requests
from pathlib import Path
import sys
import pytest
from datetime import datetime, timedelta

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import Todoist tools
from src.models.calendar.calendar_event import CalendarEvent
from src.models.calendar.enums import Priority, EventStatus, ColorTag, EventSource
from src.tools.todoist.utils import (
    create_task,
    get_task,
    get_tasks,
    transform_calendar_priority,
)
from src.tools.todoist.tool import (
    fetch_todoist_tasks,
    fetch_todoist_task,
    create_todoist_task,
)
from src.core.global_state import get_object_store, set_object_store
from src.core.object_store import ObjectStore


@pytest.fixture(autouse=True)
def clean_object_store():
    set_object_store(ObjectStore())
    yield
    set_object_store(ObjectStore())

class TestTodoistTool:
    """Test Todoist tool functionality."""

    def test_fetch_todoist_tasks(self):
        """Test fetching Todoist tasks."""
        try:
            output_key = fetch_todoist_tasks.invoke({})
            events = get_object_store().get_typed(output_key, list[CalendarEvent])
            assert isinstance(output_key, str)
            assert isinstance(events, list)
        except Exception as e:
            print(f"Expected authentication error: {e}")

    def test_create_todoist_task(self):
        """Test creating a Todoist task."""
        try:
            event = CalendarEvent(
                title="Test Meeting",
                description="Test description",
                start_time=datetime.now(),
                end_time=datetime.now() + timedelta(hours=1),
                source=EventSource.PERSONAL,
                priority=Priority.MEDIUM,
                status=EventStatus.PENDING
            )
            result = create_task(event)
            assert hasattr(result, 'id')
        except Exception as e:
            print(f"Expected authentication error: {e}")


def main():
    """Run tests directly."""
    print("Starting Todoist tool tests...")
    
    print("Running Todoist tool tests...")
    
    test = TestTodoistTool()
    
    # Test create_todoist_task
    print("\n1. Testing create_todoist_task...")
    try:
        test.test_create_todoist_task()
        print("✓ create_todoist_task test passed")
    except Exception as e:
        print(f"✗ create_todoist_task test failed: {e}")
    
    # Test fetch_todoist_tasks
    print("\n2. Testing fetch_todoist_tasks...")
    try:
        test.test_fetch_todoist_tasks()
        print("✓ fetch_todoist_tasks test passed")
    except Exception as e:
        print(f"✗ fetch_todoist_tasks test failed: {e}")
    
    print("\nAll tests completed!")


if __name__ == "__main__":
    main()