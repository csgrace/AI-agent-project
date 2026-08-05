"""Unit tests for Calendar model."""
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from datetime import datetime, date, timedelta
from src.models.calendar import Calendar, CalendarEvent, EventSource, Priority, EventStatus


class TestCalendar:
    """Test Calendar class functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create a test calendar
        self.calendar = Calendar(
            name="Test Calendar",
            description="A test calendar for unit tests"
        )
        
        # Create test events
        self.event1 = CalendarEvent(
            title="Test Event 1",
            description="First test event",
            source=EventSource.PERSONAL,
            scheduled_start=datetime(2030, 4, 2, 10, 0),
            deadline=datetime(2030, 4, 2, 11, 0),
            priority=Priority.MEDIUM,
            status=EventStatus.PENDING
        )

        self.event2 = CalendarEvent(
            title="Test Event 2",
            description="Second test event",
            source=EventSource.PERSONAL,
            scheduled_start=datetime(2030, 3, 31, 14, 0),
            deadline=datetime(2030, 3, 31, 15, 0),
            priority=Priority.HIGH,
            status=EventStatus.PENDING
        )

        self.event3 = CalendarEvent(
            title="Completed Event",
            description="A completed event",
            source=EventSource.PERSONAL,
            scheduled_start=datetime(2030, 3, 29, 9, 0),
            deadline=datetime(2030, 3, 29, 10, 0),
            priority=Priority.LOW,
            status=EventStatus.COMPLETED
        )

    def test_add_event(self):
        """Test adding an event to the calendar."""
        initial_count = len(self.calendar.events)
        added_event = self.calendar.add_event(self.event1)
        assert len(self.calendar.events) == initial_count + 1
        assert added_event in self.calendar.events
        assert added_event.id == self.event1.id

    def test_remove_event(self):
        """Test removing an event from the calendar."""
        # Add an event first
        self.calendar.add_event(self.event1)
        initial_count = len(self.calendar.events)
        
        # Remove the event
        result = self.calendar.remove_event(self.event1.id)
        assert result is True
        assert len(self.calendar.events) == initial_count - 1
        assert self.event1 not in self.calendar.events

    def test_remove_nonexistent_event(self):
        """Test removing a nonexistent event."""
        initial_count = len(self.calendar.events)
        result = self.calendar.remove_event("nonexistent_id")
        assert result is False
        assert len(self.calendar.events) == initial_count

    def test_update_event(self):
        """Test updating an event in the calendar."""
        # Add an event first
        self.calendar.add_event(self.event1)
        
        # Update the event
        new_title = "Updated Test Event"
        updated_event = self.calendar.update_event(self.event1.id, title=new_title)
        
        assert updated_event is not None
        assert updated_event.title == new_title
        assert updated_event.id == self.event1.id

    def test_update_nonexistent_event(self):
        """Test updating a nonexistent event."""
        updated_event = self.calendar.update_event("nonexistent_id", title="New Title")
        assert updated_event is None

    def test_get_event(self):
        """Test getting an event by ID."""
        # Add an event first
        self.calendar.add_event(self.event1)
        
        # Get the event
        retrieved_event = self.calendar.get_event(self.event1.id)
        assert retrieved_event is not None
        assert retrieved_event.id == self.event1.id

    def test_get_nonexistent_event(self):
        """Test getting a nonexistent event."""
        retrieved_event = self.calendar.get_event("nonexistent_id")
        assert retrieved_event is None

    def test_get_events_by_date(self):
        """Test getting events by date."""
        # Add events
        self.calendar.add_event(self.event1)  # 2026-04-02
        self.calendar.add_event(self.event2)  # 2026-03-31
        
        # Get events for 2026-04-02
        events = self.calendar.get_events_by_date(date(2030, 4, 2))
        assert len(events) == 1
        assert events[0].id == self.event1.id
        
        # Get events for 2026-03-31
        events = self.calendar.get_events_by_date(date(2030, 3, 31))
        assert len(events) == 1
        assert events[0].id == self.event2.id
        
        # Get events for a date with no events
        events = self.calendar.get_events_by_date(date(2030, 4, 1))
        assert len(events) == 0

    def test_get_events_by_date_range(self):
        """Test getting events by date range."""
        # Add events
        self.calendar.add_event(self.event1)  # 2026-04-02
        self.calendar.add_event(self.event2)  # 2026-03-31
        self.calendar.add_event(self.event3)  # 2026-03-29
        
        # Get events in range 2026-03-29 to 2026-04-02
        events = self.calendar.get_events_by_date_range(date(2030, 3, 29), date(2030, 4, 2))
        assert len(events) == 3
        assert any(event.id == self.event1.id for event in events)
        assert any(event.id == self.event2.id for event in events)
        assert any(event.id == self.event3.id for event in events)

    def test_get_todos(self):
        """Test getting todo items."""
        # Add events
        self.calendar.add_event(self.event1)  # Pending
        self.calendar.add_event(self.event2)  # Pending
        self.calendar.add_event(self.event3)  # Completed
        
        todos = self.calendar.get_todos()
        assert len(todos) == 2
        assert all(event.status not in [EventStatus.COMPLETED, EventStatus.CANCELLED] for event in todos)

    def test_get_completed_events(self):
        """Test getting completed events."""
        # Add events
        self.calendar.add_event(self.event1)  # Pending
        self.calendar.add_event(self.event3)  # Completed
        
        completed_events = self.calendar.get_completed_events()
        assert len(completed_events) == 1
        assert completed_events[0].id == self.event3.id
        assert completed_events[0].status == EventStatus.COMPLETED

    def test_get_events_by_priority(self):
        """Test getting events by priority."""
        # Add events
        self.calendar.add_event(self.event1)  # MEDIUM
        self.calendar.add_event(self.event2)  # HIGH
        
        high_priority_events = self.calendar.get_events_by_priority(Priority.HIGH)
        assert len(high_priority_events) == 1
        assert high_priority_events[0].id == self.event2.id
        
        medium_priority_events = self.calendar.get_events_by_priority(Priority.MEDIUM)
        assert len(medium_priority_events) == 1
        assert medium_priority_events[0].id == self.event1.id



    def test_get_statistics(self):
        """Test getting calendar statistics."""
        # Add events
        self.calendar.add_event(self.event1)  # MEDIUM, PENDING
        self.calendar.add_event(self.event2)  # HIGH, PENDING
        self.calendar.add_event(self.event3)  # LOW, COMPLETED
        
        stats = self.calendar.get_statistics()
        
        assert stats["total_events"] == 3
        assert stats["todo_count"] == 2
        assert stats["completed_count"] == 1
        assert stats["priority_distribution"]["HIGH"] == 1
        assert stats["priority_distribution"]["MEDIUM"] == 1
        assert stats["priority_distribution"]["LOW"] == 1
        assert stats["calendar_name"] == "Test Calendar"

    def test_clear_completed(self):
        """Test clearing completed events."""
        # Add events
        self.calendar.add_event(self.event1)  # Pending
        self.calendar.add_event(self.event3)  # Completed
        
        initial_count = len(self.calendar.events)
        removed_count = self.calendar.clear_completed()
        
        assert removed_count == 1
        assert len(self.calendar.events) == initial_count - 1
        assert all(event.status != EventStatus.COMPLETED for event in self.calendar.events)

    def test_sort_events(self):
        """Test sorting events."""
        # Add events in reverse order
        self.calendar.add_event(self.event1)  # 2026-04-02
        self.calendar.add_event(self.event2)  # 2026-03-31
        
        # Sort by start time (ascending)
        self.calendar.sort_events(key='scheduled_start')
        assert self.calendar.events[0].scheduled_start < self.calendar.events[1].scheduled_start
        assert self.calendar.events[0].id == self.event2.id
        assert self.calendar.events[1].id == self.event1.id

    def test_to_json_and_from_json(self):
        """Test JSON serialization and deserialization."""
        # Add an event
        self.calendar.add_event(self.event1)
        
        # Convert to JSON
        json_str = self.calendar.to_json()
        assert isinstance(json_str, str)
        
        # Convert back from JSON
        new_calendar = Calendar.from_json(json_str)
        assert isinstance(new_calendar, Calendar)
        assert new_calendar.name == self.calendar.name
        assert len(new_calendar.events) == len(self.calendar.events)
        assert new_calendar.events[0].id == self.event1.id

    def test_update_event_batch_normal(self):
        """Test normal batch update with same source events."""
        new_events = [
            CalendarEvent(
                title="New Event 1",
                source=EventSource.BLACKBOARD,
                scheduled_start=datetime(2026, 4, 5, 10, 0),
                deadline=datetime(2026, 4, 5, 11, 0),
                priority=Priority.HIGH,
                status=EventStatus.PENDING
            ),
            CalendarEvent(
                title="New Event 2",
                source=EventSource.BLACKBOARD,
                scheduled_start=datetime(2026, 4, 6, 14, 0),
                deadline=datetime(2026, 4, 6, 15, 0),
                priority=Priority.MEDIUM,
                status=EventStatus.PENDING
            )
        ]
        
        count = self.calendar.update_event_batch(new_events)
        assert count == 2
        assert len(self.calendar.events) == 2
        assert all(event.source == EventSource.BLACKBOARD for event in self.calendar.events)

    def test_update_event_batch_different_sources_raises_error(self):
        """Test that batch update with different sources raises ValueError."""
        mixed_events = [
            CalendarEvent(
                title="Event 1",
                source=EventSource.BLACKBOARD,
                scheduled_start=datetime(2026, 4, 5, 10, 0),
                deadline=datetime(2026, 4, 5, 11, 0),
                priority=Priority.HIGH,
                status=EventStatus.PENDING
            ),
            CalendarEvent(
                title="Event 2",
                source=EventSource.UNIVERSITY,
                scheduled_start=datetime(2026, 4, 6, 14, 0),
                deadline=datetime(2026, 4, 6, 15, 0),
                priority=Priority.MEDIUM,
                status=EventStatus.PENDING
            )
        ]
        
        with pytest.raises(ValueError) as exc_info:
            self.calendar.update_event_batch(mixed_events)
        
        assert "All events must have the same source" in str(exc_info.value)

    def test_update_event_batch_empty_list(self):
        """Test batch update with empty list returns 0."""
        count = self.calendar.update_event_batch([])
        assert count == 0
        assert len(self.calendar.events) == 0

    def test_update_event_batch_replaces_old_events(self):
        """Test that batch update replaces old events with same source."""
        old_event = CalendarEvent(
            title="Old Event",
            source=EventSource.UNIVERSITY,
            scheduled_start=datetime(2026, 4, 1, 10, 0),
            deadline=datetime(2026, 4, 1, 11, 0),
            priority=Priority.LOW,
            status=EventStatus.PENDING
        )
        self.calendar.add_event(old_event)
        self.calendar.add_event(self.event1)
        
        new_events = [
            CalendarEvent(
                title="New University Event 1",
                source=EventSource.UNIVERSITY,
                scheduled_start=datetime(2026, 4, 10, 10, 0),
                deadline=datetime(2026, 4, 10, 11, 0),
                priority=Priority.HIGH,
                status=EventStatus.PENDING
            ),
            CalendarEvent(
                title="New University Event 2",
                source=EventSource.UNIVERSITY,
                scheduled_start=datetime(2026, 4, 11, 14, 0),
                deadline=datetime(2026, 4, 11, 15, 0),
                priority=Priority.MEDIUM,
                status=EventStatus.PENDING
            )
        ]
        
        count = self.calendar.update_event_batch(new_events)
        
        assert count == 2
        assert len(self.calendar.events) == 3
        university_events = [e for e in self.calendar.events if e.source == EventSource.UNIVERSITY]
        assert len(university_events) == 2
        assert all("New University Event" in e.title for e in university_events)
        personal_events = [e for e in self.calendar.events if e.source == EventSource.PERSONAL]
        assert len(personal_events) == 1
        assert personal_events[0].id == self.event1.id


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
