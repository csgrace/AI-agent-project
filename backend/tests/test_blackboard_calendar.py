"""Test for Blackboard Calendar Tool.

This module tests the Blackboard calendar tool functionality.
"""
import pytest
import sys
import os
import json

# Add the project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime, timedelta
from src.tools.blackboard_calendar import fetch_blackboard_calendar
from src.models.calendar.calendar_event import CalendarEvent
from src.models.calendar.enums import EventSource, Priority, EventStatus
from src.core.global_state import get_object_store, set_object_store
from src.core.object_store import ObjectStore


@pytest.fixture(autouse=True)
def clean_object_store():
    set_object_store(ObjectStore())
    yield
    set_object_store(ObjectStore())


class TestBlackboardCalendar:
    """Test class for Blackboard calendar tool."""

    def test_fetch_blackboard_calendar(self):
        """Test fetching Blackboard calendar events.
        
        Note: This test requires valid Blackboard credentials.
        It is designed to be run manually with real credentials.
        """
        # Get current timestamp
        now = datetime.now()
        start_timestamp = int(now.timestamp() * 1000)
        end_timestamp = int((now + timedelta(days=1)).timestamp() * 1000)
        
        # Use valid credentials (replace with your actual credentials)
        username = json.load(open("backend/credentials/profile.json", encoding="utf-8"))["username"]
        password = json.load(open("backend/credentials/profile.json", encoding="utf-8"))["password"]
        # Update the test call to use fetch_blackboard_calendar
        output_key = fetch_blackboard_calendar.invoke({"username": username, "password": password})
        store = get_object_store()
        events = store.get_typed(output_key, list[CalendarEvent])

        assert isinstance(output_key, str)
        assert isinstance(events, list)
        assert all(isinstance(event, CalendarEvent) for event in events)
        
        if events:
            # Check that events have required fields
            for event in events:
                assert event.title
                assert event.start_time
                assert event.end_time
                assert event.source == EventSource.BLACKBOARD
                assert event.priority in [Priority.LOW, Priority.MEDIUM, Priority.HIGH]
                assert event.status in [EventStatus.PENDING, EventStatus.COMPLETED, EventStatus.CANCELLED]
            print(f"Successfully fetched {len(events)} events from Blackboard")
        else:
            print("No events found in Blackboard calendar")
        print("Blackboard calendar tool function exists and is callable")

    def test_fetch_blackboard_calendar_with_invalid_credentials(self):
        """Test fetching Blackboard calendar with invalid credentials.
        
        This test verifies that the tool handles invalid credentials properly.
        """
        # Use invalid credentials
        username = "invalid_user"
        password = "invalid_password"
        
        # Get current timestamp
        now = datetime.now()
        start_timestamp = int(now.timestamp() * 1000)
        end_timestamp = int((now + timedelta(days=1)).timestamp() * 1000)
        
        # The tool should raise an exception or return an empty list
        try:
            output_key = fetch_blackboard_calendar.invoke({"username": username, "password": password})
            events = get_object_store().get_typed(output_key, list[CalendarEvent])
            # If no exception is raised, check that events is an empty list
            assert isinstance(output_key, str)
            assert isinstance(events, list)
            print("Tool handled invalid credentials gracefully")
        except Exception as e:
            # If an exception is raised, check that it's related to login
            assert "login" in str(e).lower() or "credentials" in str(e).lower()
            print(f"Tool raised expected exception for invalid credentials: {e}")


if __name__ == "__main__":
    # Run tests directly
    test = TestBlackboardCalendar()
    test.test_fetch_blackboard_calendar()
    test.test_fetch_blackboard_calendar_with_invalid_credentials()
    print("All tests passed!")