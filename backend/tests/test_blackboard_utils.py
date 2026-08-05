"""Test script for Blackboard Calendar Tool utilities.

This script tests the utility functions in utils.py directly.
"""
import sys
import os
import json

# Add the project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the utility functions
from src.tools.blackboard_calendar.utils import (
    cas_login,
    fetch_all_time_periods,
    convert_bb_events_to_calendar_events
)


def test_cas_login():
    """Test CAS login functionality."""
    print("\nTesting CAS login...")
    
    # Replace with your actual credentials
    username = json.load(open("backend/credentials/profile.json", encoding="utf-8"))["username"]
    password = json.load(open("backend/credentials/profile.json", encoding="utf-8"))["password"]
    
    try:
        cookies = cas_login(username, password)
        print(f"CAS login successful! Got cookies: {list(cookies.keys())}")
        assert cookies, "No cookies returned"
        print("CAS login test passed!")
        return cookies
    except Exception as e:
        print(f"CAS login test failed: {e}")
        return None


def test_fetch_all_time_periods(username, password):
    """Test fetching all time periods from Blackboard."""
    print("\nTesting fetch_all_time_periods...")
    
    try:
        all_events = fetch_all_time_periods(username, password)
        print(f"Fetched {len(all_events)} events from Blackboard")
        assert isinstance(all_events, list), "Expected list of events"
        print("fetch_all_time_periods test passed!")
        return all_events
    except Exception as e:
        print(f"fetch_all_time_periods test failed: {e}")
        return None


def test_convert_bb_events_to_calendar_events(bb_events):
    """Test converting Blackboard events to CalendarEvent objects."""
    print("\nTesting convert_bb_events_to_calendar_events...")
    
    if not bb_events:
        print("No events to convert, skipping test")
        return None
    
    try:
        calendar_events = convert_bb_events_to_calendar_events(bb_events)
        print(f"Converted {len(calendar_events)} events to CalendarEvent format")
        assert isinstance(calendar_events, list), "Expected list of CalendarEvent objects"
        if calendar_events:
            print(f"First event: {calendar_events[0].title}")
        print("convert_bb_events_to_calendar_events test passed!")
        return calendar_events
    except Exception as e:
        print(f"convert_bb_events_to_calendar_events test failed: {e}")
        return None


def main():
    """Run all tests."""
    print("Running Blackboard Calendar Tool utility tests...")
    
    # Test CAS login
    
    username = json.load(open("backend/credentials/profile.json", encoding="utf-8"))["username"]
    password = json.load(open("backend/credentials/profile.json", encoding="utf-8"))["password"]

    
    # Test fetching all time periods
    bb_events = test_fetch_all_time_periods(username, password)
    
    # Test converting events
    calendar_events = test_convert_bb_events_to_calendar_events(bb_events)
    
    print("\nAll tests completed!")


if __name__ == "__main__":
    main()