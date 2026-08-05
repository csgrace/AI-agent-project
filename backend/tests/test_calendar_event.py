"""Unit tests for CalendarEvent model."""
import pytest
import json
from datetime import datetime, timedelta, timezone
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.models.calendar.calendar_event import CalendarEvent
from src.models.calendar.enums import EventSource, Priority, EventStatus, ColorTag
from src.models.calendar.recurring_rules import RecurringRule


class TestCalendarEventCreation:
    """Test basic event creation."""

    def test_create_basic_event(self):
        """Test creating a basic event with required fields."""
        now = datetime.now()
        later = now + timedelta(days=3)

        event = CalendarEvent(
            title="Test Meeting",
            scheduled_start=now,
            deadline=later,
            source=EventSource.UNIVERSITY,
            priority=Priority.MEDIUM,
            status=EventStatus.PENDING
        )

        assert event.title == "Test Meeting"
        assert event.scheduled_start == now
        assert event.deadline == later
        assert event.source == EventSource.UNIVERSITY
        assert event.priority == Priority.MEDIUM
        assert event.status == EventStatus.PENDING
        assert event.id.startswith("event_")
        assert len(event.id) == 14  # "event_" + 8 chars

    def test_create_event_with_all_fields(self):
        """Test creating an event with all optional fields."""
        now = datetime.now()
        later = now + timedelta(hours=3)

        event = CalendarEvent(
            title="CS304 Final Project",
            description="Submit final report and code",
            scheduled_start=now,
            deadline=later,
            source=EventSource.BLACKBOARD,
            location="Online",
            priority=Priority.HIGH,
            status=EventStatus.PENDING,
            tags=["project", "cs304"],
            metadata={
                "course_code": "CS304",
                "points": 100,
                "submission_link": "https://bb.sustech.edu.cn"
            }
        )

        assert event.description == "Submit final report and code"
        assert event.location == "Online"
        assert event.priority == Priority.HIGH
        assert event.tags == ["project", "cs304"]
        assert event.metadata["course_code"] == "CS304"
        assert event.metadata["points"] == 100

    def test_create_event_with_different_sources(self):
        """Test creating events from different sources."""
        now = datetime.now()
        later = now + timedelta(hours=1)

        # University event
        uni_event = CalendarEvent(
            title="University Lecture",
            scheduled_start=now,
            deadline=later,
            source=EventSource.UNIVERSITY,
            priority=Priority.MEDIUM,
            status=EventStatus.PENDING
        )
        assert uni_event.source == EventSource.UNIVERSITY

        # Blackboard event
        bb_event = CalendarEvent(
            title="Homework Due",
            scheduled_start=now,
            deadline=later,
            source=EventSource.BLACKBOARD,
            priority=Priority.MEDIUM,
            status=EventStatus.PENDING
        )
        assert bb_event.source == EventSource.BLACKBOARD

        # Personal event
        personal_event = CalendarEvent(
            title="Study Session",
            scheduled_start=now,
            deadline=later,
            source=EventSource.PERSONAL,
            priority=Priority.MEDIUM,
            status=EventStatus.PENDING
        )
        assert personal_event.source == EventSource.PERSONAL


class TestEventValidation:
    """Test event validation rules."""

    def test_deadline_after_scheduled_start(self):
        """Test that deadline must be after scheduled_start."""
        now = datetime.now()
        earlier = now - timedelta(hours=1)

        with pytest.raises(ValueError, match="deadline must be after scheduled_start"):
            CalendarEvent(
                title="Invalid Event",
                scheduled_start=now,
                deadline=earlier,
                source=EventSource.PERSONAL
            )

    def test_auto_upgrade_priority_for_urgent_events(self):
        """Test priority auto-upgrade for events within 48 hours."""
        # Create event due in 24 hours
        due_soon = datetime.now() + timedelta(hours=24)

        event = CalendarEvent(
            title="Urgent Deadline",
            scheduled_start=datetime.now(),
            deadline=due_soon,
            source=EventSource.BLACKBOARD,
            priority=Priority.MEDIUM,
            status=EventStatus.PENDING
        )

        # Should be auto-upgraded to HIGH
        assert event.priority == Priority.HIGH

    def test_priority_not_upgraded_for_future_events(self):
        """Test priority not upgraded for events far in future."""
        # Create event due in 7 days
        due_future = datetime.now() + timedelta(days=7)

        event = CalendarEvent(
            title="Future Task",
            scheduled_start=datetime.now(),
            deadline=due_future,
            source=EventSource.PERSONAL,
            priority=Priority.MEDIUM,
            status=EventStatus.PENDING
        )

        # Should remain MEDIUM
        assert event.priority == Priority.MEDIUM

    def test_timezone_aware_deadline_does_not_crash_priority_upgrade_or_serialization(self):
        """Aware datetimes should not fail on now/deadline arithmetic or serialization."""
        now_aware = datetime.now(timezone.utc)
        due_soon = now_aware + timedelta(hours=24)

        event = CalendarEvent(
            title="Aware Event",
            scheduled_start=now_aware,
            deadline=due_soon,
            source=EventSource.PERSONAL,
            priority=Priority.MEDIUM,
            status=EventStatus.PENDING,
        )

        assert event.priority == Priority.HIGH
        assert isinstance(event.to_json(), str)

    def test_aware_input_is_normalized_to_cn_naive(self):
        aware_start = datetime.fromisoformat("2026-04-18T09:00:00+00:00")
        aware_deadline = datetime.fromisoformat("2026-04-18T11:00:00+00:00")

        event = CalendarEvent(
            title="Normalize Aware",
            scheduled_start=aware_start,
            deadline=aware_deadline,
            source=EventSource.PERSONAL,
            priority=Priority.MEDIUM,
            status=EventStatus.PENDING,
        )

        assert event.scheduled_start.tzinfo is None
        assert event.deadline.tzinfo is None
        # UTC+0 -> Asia/Shanghai (+8)
        assert event.scheduled_start.hour == 17
        assert event.deadline.hour == 19

    def test_recurring_event_with_valid_rule(self):
        """Test recurring event with valid rule."""
        now = datetime.now()
        later = now + timedelta(hours=1)

        rule = RecurringRule(
            frequency="weekly",
            interval=1,
            weekdays=[2],  # Wednesday
            count=10
        )

        event = CalendarEvent(
            title="Weekly Class",
            scheduled_start=now,
            deadline=later,
            source=EventSource.UNIVERSITY,
            recurring_rule=rule,
            priority=Priority.MEDIUM,
            status=EventStatus.PENDING
        )

        assert event.is_recurring
        assert event.recurring_rule == rule
        assert event.recurring_rule.frequency == "weekly"
        assert event.recurring_rule.weekdays == [2]


class TestEventProperties:
    """Test event property calculations."""

    def test_duration_minutes(self):
        """Test duration calculation."""
        start = datetime(2026, 4, 15, 10, 0)
        end = datetime(2026, 4, 15, 12, 30)

        event = CalendarEvent(
            title="Test Duration",
            scheduled_start=start,
            deadline=end,
            source=EventSource.PERSONAL,
            priority=Priority.MEDIUM,
            status=EventStatus.PENDING
        )

        assert event.duration_minutes == 150  # 2.5 hours

    def test_is_overdue(self):
        """Test overdue check."""
        # Past event
        past = datetime.now() - timedelta(hours=1)

        past_event = CalendarEvent(
            title="Past Event",
            scheduled_start=past,
            deadline=past + timedelta(minutes=1),
            source=EventSource.PERSONAL,
            priority=Priority.MEDIUM,
            status=EventStatus.PENDING
        )
        assert past_event.is_overdue is True

        # Future event
        future = datetime.now() + timedelta(hours=1)

        future_event = CalendarEvent(
            title="Future Event",
            scheduled_start=future,
            deadline=future + timedelta(minutes=1),
            source=EventSource.PERSONAL,
            priority=Priority.MEDIUM,
            status=EventStatus.PENDING
        )
        assert future_event.is_overdue is False

        # Completed event
        completed_event = CalendarEvent(
            title="Completed Event",
            scheduled_start=past,
            deadline=past + timedelta(minutes=1),
            source=EventSource.PERSONAL,
            priority=Priority.MEDIUM,
            status=EventStatus.COMPLETED
        )
        assert completed_event.is_overdue is False

    def test_is_recurring(self):
        """Test recurring event detection."""
        now = datetime.now()
        later = now + timedelta(hours=1)

        # Non-recurring event
        single_event = CalendarEvent(
            title="Single",
            scheduled_start=now,
            deadline=later,
            source=EventSource.PERSONAL,
            priority=Priority.MEDIUM,
            status=EventStatus.PENDING
        )
        assert single_event.is_recurring is False

        # Recurring event
        rule = RecurringRule(
            frequency="daily",
            interval=1,
            count=5
        )
        recurring_event = CalendarEvent(
            title="Daily Task",
            scheduled_start=now,
            deadline=later,
            source=EventSource.PERSONAL,
            recurring_rule=rule,
            priority=Priority.MEDIUM,
            status=EventStatus.PENDING
        )
        assert recurring_event.is_recurring is True


class TestEventSerialization:
    """Test JSON serialization and deserialization."""

    def test_to_json_with_none_priority_and_status(self):
        """Serialization should support optional enum fields being None."""
        start = datetime(2026, 4, 15, 14, 0)
        end = datetime(2026, 4, 15, 16, 0)

        event = CalendarEvent(
            title="Optional Enum Fields",
            scheduled_start=start,
            deadline=end,
            source=EventSource.PERSONAL,
        )

        json_str = event.to_json()
        data = json.loads(json_str)

        assert data["priority"] is None
        assert data["status"] is None

    def test_to_json(self):
        """Test converting event to JSON."""
        start = datetime(2026, 4, 15, 14, 0)
        end = datetime(2026, 4, 15, 16, 0)

        event = CalendarEvent(
            title="Study Session",
            scheduled_start=start,
            deadline=end,
            source=EventSource.PERSONAL,
            location="Library",
            priority=Priority.MEDIUM,
            status=EventStatus.PENDING,
            tags=["study", "exam"]
        )

        json_str = event.to_json()
        data = json.loads(json_str)

        assert data["title"] == "Study Session"
        assert data["source"] == "personal"
        assert data["location"] == "Library"
        assert data["tags"] == ["study", "exam"]
        assert "scheduled_start" in data
        assert "deadline" in data
        assert "duration_minutes" in data
        assert "is_overdue" in data

    def test_from_json(self):
        """Test creating event from JSON."""
        json_str = '''
        {
            "id": "event_12345678",
            "title": "Test Event",
            "description": "Test description",
            "source": "university",
            "scheduled_start": "2026-04-15T10:00:00",
            "deadline": "2026-04-15T12:00:00",
            "location": "Room 101",
            "priority": "high",
            "status": "pending",
            "color_tag": "red",
            "tags": ["test"],
            "metadata": {"key": "value"}
        }
        '''

        event = CalendarEvent.from_json(json_str)

        assert event.title == "Test Event"
        assert event.source == EventSource.UNIVERSITY
        assert event.priority == Priority.HIGH
        assert event.location == "Room 101"
        assert event.tags == ["test"]
        assert event.metadata["key"] == "value"

    def test_from_json_allows_none_optional_enums(self):
        """from_json should accept null priority/status fields."""
        json_str = '''
        {
            "id": "event_nullopt",
            "title": "Null Optional Enums",
            "description": null,
            "source": "personal",
            "scheduled_start": "2026-04-15T10:00:00",
            "deadline": "2026-04-15T12:00:00",
            "duration": null,
            "location": null,
            "priority": null,
            "status": null,
            "category": "unknown",
            "recurring_rule": null,
            "color_tag": "blue",
            "tags": [],
            "metadata": {}
        }
        '''

        event = CalendarEvent.from_json(json_str)

        assert event.priority is None
        assert event.status is None

    def test_round_trip_serialization(self):
        """Test that serialization round trip preserves all data."""
        start = datetime(2026, 4, 15, 14, 0, 30)
        end = datetime(2026, 4, 15, 16, 0, 30)

        original = CalendarEvent(
            title="Round Trip Test",
            description="Testing serialization",
            scheduled_start=start,
            deadline=end,
            source="blackboard",
            location="Online",
            priority=Priority.HIGH,
            status=EventStatus.PENDING,
            tags=["test", "serialization"],
            metadata={"test_id": 123}
        )

        # Serialize
        json_str = original.to_json()

        # Deserialize
        restored = CalendarEvent.from_json(json_str)

        # Compare
        assert restored.title == original.title
        assert restored.description == original.description
        assert restored.scheduled_start == original.scheduled_start
        assert restored.deadline == original.deadline
        assert restored.source == original.source
        assert restored.location == original.location
        assert restored.priority == original.priority
        assert restored.tags == original.tags
        assert restored.metadata == original.metadata


class TestEventHelperMethods:
    """Test event helper methods."""

    def test_update_method(self):
        """Test updating event fields."""
        now = datetime.now()
        later = now + timedelta(hours=1)

        event = CalendarEvent(
            title="Original Title",
            scheduled_start=now,
            deadline=later,
            source=EventSource.PERSONAL,
            priority=Priority.MEDIUM,
            status=EventStatus.PENDING
        )

        original_updated_at = event.updated_at

        # Update title and location
        event.update(
            title="Updated Title",
            location="New Location"
        )

        assert event.title == "Updated Title"
        assert event.location == "New Location"

    def test_complete_method(self):
        """Test marking event as completed."""
        now = datetime.now()
        later = now + timedelta(hours=1)

        event = CalendarEvent(
            title="Task to Complete",
            scheduled_start=now,
            deadline=later,
            source=EventSource.PERSONAL,
            priority=Priority.MEDIUM,
            status=EventStatus.PENDING
        )

        assert event.status == EventStatus.PENDING

        event.complete()

        assert event.status == EventStatus.COMPLETED

    def test_cancel_method(self):
        """Test canceling event."""
        now = datetime.now()
        later = now + timedelta(hours=1)

        event = CalendarEvent(
            title="Event to Cancel",
            scheduled_start=now,
            deadline=later,
            source=EventSource.PERSONAL,
            priority=Priority.MEDIUM,
            status=EventStatus.PENDING
        )

        event.cancel()

        assert event.status == EventStatus.CANCELLED

    def test_format_for_display(self):
        """Test display formatting."""
        start = datetime(2026, 4, 15, 14, 0)
        end = datetime(2026, 4, 15, 16, 0)

        event = CalendarEvent(
            title="Study Session",
            scheduled_start=start,
            deadline=end,
            source=EventSource.PERSONAL,
            location="Library",
            priority=Priority.MEDIUM,
            status=EventStatus.PENDING,
            description="This is a long description that might be truncated"
        )

        display = event.format_for_display()

        assert "Study Session" in display
        assert "Library" in display
        assert "14:00" in display
        assert "16:00" in display


class TestColorTag:
    """Test color tag functionality."""

    def test_random_color_assignment(self):
        """Test that events get random colors."""
        now = datetime.now()
        later = now + timedelta(hours=1)

        # Create multiple events and check they might have different colors
        event1 = CalendarEvent(
            title="Event 1",
            scheduled_start=now,
            deadline=later,
            source=EventSource.PERSONAL,
            priority=Priority.MEDIUM,
            status=EventStatus.PENDING
        )

        event2 = CalendarEvent(
            title="Event 2",
            scheduled_start=now,
            deadline=later,
            source=EventSource.PERSONAL,
            priority=Priority.MEDIUM,
            status=EventStatus.PENDING
        )

        # Colors should be valid ColorTag enum values
        assert event1.color_tag in list(ColorTag)
        assert event2.color_tag in list(ColorTag)

    def test_manual_color_assignment(self):
        """Test manually assigning a color."""
        now = datetime.now()
        later = now + timedelta(hours=1)

        event = CalendarEvent(
            title="Red Event",
            scheduled_start=now,
            deadline=later,
            source=EventSource.PERSONAL,
            priority=Priority.MEDIUM,
            status=EventStatus.PENDING,
            color_tag=ColorTag.RED
        )

        assert event.color_tag == ColorTag.RED


class TestEventID:
    """Test event ID generation."""

    def test_unique_ids(self):
        """Test that each event gets a unique ID."""
        now = datetime.now()
        later = now + timedelta(hours=1)

        events = []
        for i in range(10):
            event = CalendarEvent(
                title=f"Event {i}",
                scheduled_start=now,
                deadline=later,
                source=EventSource.PERSONAL,
                priority=Priority.MEDIUM,
                status=EventStatus.PENDING
            )
            events.append(event)

        ids = [e.id for e in events]
        assert len(ids) == len(set(ids))  # All IDs should be unique

    def test_id_format(self):
        """Test ID format."""
        now = datetime.now()
        later = now + timedelta(hours=1)

        event = CalendarEvent(
            title="Test",
            scheduled_start=now,
            deadline=later,
            source=EventSource.PERSONAL,
            priority=Priority.MEDIUM,
            status=EventStatus.PENDING
        )

        assert event.id.startswith("event_")
        assert len(event.id) == 14  # "event_" + 8 hex chars
        # Check that the part after event_ is hex
        hex_part = event.id[6:]
        assert all(c in "0123456789abcdef" for c in hex_part)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])