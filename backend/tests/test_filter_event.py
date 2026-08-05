"""Unit tests for filter_event tool."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.models.calendar.calendar_event import CalendarEvent
from src.models.calendar.simple_event import SimpleEvent
from src.models.calendar.enums import EventSource, Priority, EventStatus, ColorTag
from src.models.calendar.calendar import Calendar
from src.tools.filter_event.tool import filter_events_by_time_range_and_prompt
from src.tools.filter_event.utils import (
    convert_to_simple_event,
    check_event_matches_prompt,
    filter_events_with_llm
)
from src.core.global_state import set_calendar, get_calendar, get_object_store, set_object_store
from src.core.object_store import ObjectStore


@pytest.fixture(autouse=True)
def clean_object_store():
    set_object_store(ObjectStore())
    yield
    set_object_store(ObjectStore())


def _fetch_simple_events(output_key: str) -> list[SimpleEvent]:
    return get_object_store().get_typed(output_key, list[SimpleEvent])


class TestConvertToSimpleEvent:
    """Test conversion from CalendarEvent to SimpleEvent."""

    def test_convert_basic_event(self):
        """Test converting a basic CalendarEvent to SimpleEvent."""
        now = datetime.now()
        later = now + timedelta(hours=2)
        
        calendar_event = CalendarEvent(
            title="Test Meeting",
            description="A test meeting",
            start_time=now,
            end_time=later,
            source=EventSource.UNIVERSITY,
            priority=Priority.HIGH,
            status=EventStatus.PENDING,
            location="Room 101",
            color_tag=ColorTag.BLUE
        )
        
        simple_event = convert_to_simple_event(calendar_event)
        
        assert simple_event.title == "Test Meeting"
        assert simple_event.description == "A test meeting"
        assert simple_event.start_time == now
        assert simple_event.end_time == later
        assert simple_event.duration == timedelta(hours=2)
        assert simple_event.priority == Priority.HIGH
        assert simple_event.location == "Room 101"
        assert simple_event.color_tag == ColorTag.BLUE

    def test_convert_event_without_optional_fields(self):
        """Test converting an event without optional fields."""
        now = datetime.now()
        later = now + timedelta(days=1)
        
        calendar_event = CalendarEvent(
            title="Simple Event",
            start_time=now,
            end_time=later,
            source=EventSource.TODOIST
        )
        
        simple_event = convert_to_simple_event(calendar_event)
        
        assert simple_event.title == "Simple Event"
        assert simple_event.description is None
        assert simple_event.duration == timedelta(days=1)
        assert simple_event.priority == Priority.MEDIUM
        assert simple_event.location is None
        assert simple_event.color_tag is None

    def test_duration_calculation(self):
        """Test that duration is correctly calculated."""
        now = datetime.now()
        later = now + timedelta(hours=3, minutes=30)
        
        calendar_event = CalendarEvent(
            title="Long Meeting",
            start_time=now,
            end_time=later,
            source=EventSource.UNIVERSITY
        )
        
        simple_event = convert_to_simple_event(calendar_event)
        
        assert simple_event.duration == timedelta(hours=3, minutes=30)
        assert simple_event.duration_minutes == 210


class TestFilterEventsByTimeRange:
    """Test time range filtering functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.now = datetime.now()
        self.calendar = Calendar(name="Test Calendar")
        
        self.event1 = CalendarEvent(
            title="Event 1",
            start_time=self.now,
            end_time=self.now + timedelta(hours=1),
            source=EventSource.UNIVERSITY,
            status=EventStatus.PENDING
        )
        
        self.event2 = CalendarEvent(
            title="Event 2",
            start_time=self.now + timedelta(days=1),
            end_time=self.now + timedelta(days=1, hours=1),
            source=EventSource.UNIVERSITY,
            status=EventStatus.IN_PROGRESS
        )
        
        self.event3 = CalendarEvent(
            title="Event 3",
            start_time=self.now + timedelta(days=2),
            end_time=self.now + timedelta(days=2, hours=1),
            source=EventSource.UNIVERSITY,
            status=EventStatus.COMPLETED
        )
        
        self.calendar.add_event(self.event1)
        self.calendar.add_event(self.event2)
        self.calendar.add_event(self.event3)
        
        set_calendar(self.calendar)

    def test_filter_events_in_range(self):
        """Test filtering events within a specific time range."""
        start_time = self.now
        end_time = self.now + timedelta(days=1, hours=2)
        
        output_key = filter_events_by_time_range_and_prompt(start_time, end_time)
        filtered = _fetch_simple_events(output_key)
        
        assert len(filtered) == 1
        assert filtered[0].title == "Event 1"

    def test_filter_events_no_match(self):
        """Test filtering when no events match the time range."""
        start_time = self.now + timedelta(days=10)
        end_time = self.now + timedelta(days=11)
        
        output_key = filter_events_by_time_range_and_prompt(start_time, end_time)
        filtered = _fetch_simple_events(output_key)
        
        assert len(filtered) == 0

    def test_filter_events_all_match(self):
        """Test filtering when all events match the time range."""
        start_time = self.now
        end_time = self.now + timedelta(days=3)
        
        output_key = filter_events_by_time_range_and_prompt(start_time, end_time)
        filtered = _fetch_simple_events(output_key)
        
        assert len(filtered) == 2

    def test_filter_events_empty_calendar(self):
        """Test filtering when calendar is empty."""
        empty_calendar = Calendar(name="Empty Calendar")
        set_calendar(empty_calendar)
        
        start_time = self.now
        end_time = self.now + timedelta(days=1)
        
        output_key = filter_events_by_time_range_and_prompt(start_time, end_time)
        filtered = _fetch_simple_events(output_key)
        
        assert len(filtered) == 0

    def test_filter_events_no_calendar(self):
        """Test filtering when global calendar is not set."""
        set_calendar(None)
        
        start_time = self.now
        end_time = self.now + timedelta(days=1)
        
        output_key = filter_events_by_time_range_and_prompt(start_time, end_time)
        filtered = _fetch_simple_events(output_key)
        
        assert len(filtered) == 0

    def test_filter_events_invalid_time_range(self):
        """Test filtering with invalid time range (start > end)."""
        start_time = self.now + timedelta(days=1)
        end_time = self.now
        
        with pytest.raises(ValueError, match="start_time must be before or equal to end_time"):
            filter_events_by_time_range_and_prompt(start_time, end_time)


class TestFilterEventsWithLLM:
    """Test LLM-based semantic filtering."""

    def setup_method(self):
        """Set up test fixtures."""
        self.now = datetime.now()
        
        self.event1 = CalendarEvent(
            title="CS304 Final Exam",
            description="Computer Science final examination",
            start_time=self.now,
            end_time=self.now + timedelta(hours=2),
            source=EventSource.UNIVERSITY,
            priority=Priority.HIGH
        )
        
        self.event2 = CalendarEvent(
            title="Team Meeting",
            description="Weekly team standup meeting",
            start_time=self.now + timedelta(days=1),
            end_time=self.now + timedelta(days=1, hours=1),
            source=EventSource.UNIVERSITY,
            priority=Priority.MEDIUM
        )
        
        self.event3 = CalendarEvent(
            title="Math Quiz",
            description="Midterm quiz for Calculus II",
            start_time=self.now + timedelta(days=2),
            end_time=self.now + timedelta(days=2, hours=1),
            source=EventSource.UNIVERSITY,
            priority=Priority.HIGH
        )

    @patch('src.tools.filter_event.utils.ChatOpenAI')
    def test_filter_with_llm_exam_events(self, mock_llm_class):
        """Test filtering for exam-related events using LLM."""
        from src.tools.filter_event.utils import EventMatchResult
        
        mock_chain = MagicMock()
        mock_chain.batch.return_value = [
            EventMatchResult(matches=True, reason="Event is exam-related"),
            EventMatchResult(matches=False, reason="Event is not exam-related"),
            EventMatchResult(matches=True, reason="Event is exam-related")
        ]
        
        with patch('src.tools.filter_event.utils.llm', mock_llm_class):
            with patch('src.tools.filter_event.utils.ChatPromptTemplate') as mock_prompt:
                mock_prompt_instance = MagicMock()
                mock_prompt.from_messages.return_value.partial.return_value = mock_prompt_instance
                
                with patch('src.tools.filter_event.utils.PydanticOutputParser') as mock_parser:
                    mock_parser_instance = MagicMock()
                    mock_parser.return_value = mock_parser_instance
                    
                    events = [self.event1, self.event2, self.event3]
                    
                    with patch('src.tools.filter_event.utils.chain', mock_chain):
                        filtered = filter_events_with_llm(events, "all exam-related events")
                        
                        assert len(filtered) == 2
                        assert filtered[0].title == "CS304 Final Exam"
                        assert filtered[1].title == "Math Quiz"

    @patch('src.tools.filter_event.utils.ChatOpenAI')
    def test_filter_with_llm_high_priority(self, mock_llm_class):
        """Test filtering for high priority events using LLM."""
        from src.tools.filter_event.utils import EventMatchResult
        
        mock_chain = MagicMock()
        mock_chain.batch.return_value = [
            EventMatchResult(matches=True, reason="Event is high priority"),
            EventMatchResult(matches=False, reason="Event is not high priority"),
            EventMatchResult(matches=True, reason="Event is high priority")
        ]
        
        with patch('src.tools.filter_event.utils.llm', mock_llm_class):
            with patch('src.tools.filter_event.utils.ChatPromptTemplate') as mock_prompt:
                mock_prompt_instance = MagicMock()
                mock_prompt.from_messages.return_value.partial.return_value = mock_prompt_instance
                
                with patch('src.tools.filter_event.utils.PydanticOutputParser') as mock_parser:
                    mock_parser_instance = MagicMock()
                    mock_parser.return_value = mock_parser_instance
                    
                    events = [self.event1, self.event2, self.event3]
                    
                    with patch('src.tools.filter_event.utils.chain', mock_chain):
                        filtered = filter_events_with_llm(events, "high priority events")
                        
                        assert len(filtered) == 2
                        assert filtered[0].title == "CS304 Final Exam"
                        assert filtered[1].title == "Math Quiz"

    @patch('src.tools.filter_event.utils.ChatOpenAI')
    def test_filter_with_llm_no_match(self, mock_llm_class):
        """Test filtering when no events match the prompt."""
        from src.tools.filter_event.utils import EventMatchResult
        
        mock_chain = MagicMock()
        mock_chain.batch.return_value = [
            EventMatchResult(matches=False, reason="No match"),
            EventMatchResult(matches=False, reason="No match"),
            EventMatchResult(matches=False, reason="No match")
        ]
        
        with patch('src.tools.filter_event.utils.llm', mock_llm_class):
            with patch('src.tools.filter_event.utils.ChatPromptTemplate') as mock_prompt:
                mock_prompt_instance = MagicMock()
                mock_prompt.from_messages.return_value.partial.return_value = mock_prompt_instance
                
                with patch('src.tools.filter_event.utils.PydanticOutputParser') as mock_parser:
                    mock_parser_instance = MagicMock()
                    mock_parser.return_value = mock_parser_instance
                    
                    events = [self.event1, self.event2, self.event3]
                    
                    with patch('src.tools.filter_event.utils.chain', mock_chain):
                        filtered = filter_events_with_llm(events, "non-existent events")
                        
                        assert len(filtered) == 0


class TestIntegrationFilterEvents:
    """Integration tests for the complete filtering workflow."""

    def setup_method(self):
        """Set up test fixtures."""
        self.now = datetime.now()
        self.calendar = Calendar(name="Test Calendar")
        
        self.exam_event = CalendarEvent(
            title="CS304 Final Exam",
            description="Computer Science final examination",
            start_time=self.now,
            end_time=self.now + timedelta(hours=2),
            source=EventSource.UNIVERSITY,
            priority=Priority.HIGH,
            status=EventStatus.PENDING
        )
        
        self.meeting_event = CalendarEvent(
            title="Team Meeting",
            description="Weekly team standup meeting",
            start_time=self.now + timedelta(days=1),
            end_time=self.now + timedelta(days=1, hours=1),
            source=EventSource.UNIVERSITY,
            priority=Priority.MEDIUM,
            status=EventStatus.IN_PROGRESS
        )
        
        self.quiz_event = CalendarEvent(
            title="Math Quiz",
            description="Midterm quiz for Calculus II",
            start_time=self.now + timedelta(days=2),
            end_time=self.now + timedelta(days=2, hours=1),
            source=EventSource.UNIVERSITY,
            priority=Priority.HIGH,
            status=EventStatus.COMPLETED
        )
        
        self.calendar.add_event(self.exam_event)
        self.calendar.add_event(self.meeting_event)
        self.calendar.add_event(self.quiz_event)
        
        set_calendar(self.calendar)

    def test_integration_time_filter_only(self):
        """Test complete workflow with time filtering only."""
        start_time = self.now
        end_time = self.now + timedelta(hours=3)
        
        output_key = filter_events_by_time_range_and_prompt(start_time, end_time)
        filtered = _fetch_simple_events(output_key)
        
        assert len(filtered) == 1
        assert filtered[0].title == "CS304 Final Exam"
        assert isinstance(filtered[0], SimpleEvent)

    @patch('src.tools.filter_event.utils.filter_events_with_llm')
    def test_integration_time_and_llm_filter(self, mock_filter_llm):
        """Test complete workflow with both time and LLM filtering."""
        mock_filter_llm.return_value = [self.exam_event, self.meeting_event]
        
        start_time = self.now
        end_time = self.now + timedelta(days=3)
        
        output_key = filter_events_by_time_range_and_prompt(
            start_time, end_time, prompt="exam-related events"
        )
        filtered = _fetch_simple_events(output_key)
        
        assert len(filtered) == 2
        assert filtered[0].title == "CS304 Final Exam"
        assert filtered[1].title == "Team Meeting"

    def test_integration_no_events_in_range(self):
        """Test workflow when no events are in the time range."""
        start_time = self.now + timedelta(days=10)
        end_time = self.now + timedelta(days=11)
        
        output_key = filter_events_by_time_range_and_prompt(start_time, end_time)
        filtered = _fetch_simple_events(output_key)
        
        assert len(filtered) == 0

    @patch('src.tools.filter_event.utils.filter_events_with_llm')
    def test_integration_llm_filter_failure(self, mock_filter_llm):
        """Test workflow when LLM filtering fails."""
        mock_filter_llm.side_effect = Exception("LLM service unavailable")
        
        start_time = self.now
        end_time = self.now + timedelta(days=3)
        
        output_key = filter_events_by_time_range_and_prompt(
            start_time, end_time, prompt="exam-related events"
        )
        filtered = _fetch_simple_events(output_key)
        
        assert len(filtered) == 2


class TestSimpleEventDuration:
    """Test SimpleEvent duration field with timedelta."""

    def test_simple_event_duration_timedelta(self):
        """Test that SimpleEvent duration is a timedelta."""
        now = datetime.now()
        later = now + timedelta(hours=2, minutes=30)
        
        simple_event = SimpleEvent(
            title="Test Event",
            start_time=now,
            end_time=later,
            duration=timedelta(hours=2, minutes=30),
            priority=Priority.HIGH
        )
        
        assert isinstance(simple_event.duration, timedelta)
        assert simple_event.duration == timedelta(hours=2, minutes=30)
        assert simple_event.duration_minutes == 150

    def test_simple_event_duration_minutes_calculation(self):
        """Test duration_minutes property calculation."""
        now = datetime.now()
        
        simple_event = SimpleEvent(
            title="Test Event",
            start_time=now,
            end_time=now + timedelta(days=1),
            duration=timedelta(days=1),
            priority=Priority.MEDIUM
        )
        
        assert simple_event.duration_minutes == 1440
