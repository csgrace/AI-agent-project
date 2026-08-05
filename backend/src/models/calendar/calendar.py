"""Calendar class for managing events and todos with calendar view capabilities."""
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field
import uuid


from .calendar_event import CalendarEvent
from .enums import EventStatus, Priority


class Calendar(BaseModel):
    """
    Calendar class for managing events and todos with calendar view capabilities.
    """

    # ========== Basic Information ==========
    id: str = Field(
        default_factory=lambda: f"calendar_{uuid.uuid4().hex[:8]}",
        description="Unique calendar identifier"
    )
    name: str = Field(..., min_length=1, max_length=200, description="Calendar name")
    description: Optional[str] = Field(None, max_length=1000, description="Calendar description")
    
    # ========== Events Management ==========
    events: List[CalendarEvent] = Field(default_factory=list, description="List of events in the calendar")
    
    # ========== Metadata ==========
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")

    # ========== Calendar View Methods ==========

    def add_event(self, event: CalendarEvent) -> CalendarEvent:
        """Add an event to the calendar.
        
        Args:
            event: The event to add
            
        Returns:
            The added event
        """
        self.events.append(event)
        self.updated_at = datetime.now()
        return event

    def remove_event(self, event_id: str) -> bool:
        """Remove an event from the calendar.
        
        Args:
            event_id: The ID of the event to remove
            
        Returns:
            True if the event was removed, False otherwise
        """
        initial_length = len(self.events)
        self.events = [event for event in self.events if event.id != event_id]
        if len(self.events) < initial_length:
            self.updated_at = datetime.now()
            return True
        return False

    def sync_draft(self, draft_calendar: 'DraftCalendar', partial_update: bool = False) -> int:
        """Sync events from draft calendar to main calendar.
        
        Args:
            draft_calendar: DraftCalendar object to sync from
            partial_update: If True, use partial update mode; otherwise use full update mode
                    
        Returns:
            Number of events synced
        """
        if not draft_calendar.events:
            return 0
        
        if not partial_update:
            # Full update mode: remove all events with the same sources as in draft
            # First, collect all sources from draft events
            sources = set()
            for event in draft_calendar.events:
                sources.add(event.source)
            
            # Remove existing events with these sources
            events_to_remove = [
                event.id for event in self.events 
                if event.source in sources
            ]
            for event_id in events_to_remove:
                self.remove_event(event_id)
            
            # Add all draft events
            for event in draft_calendar.events:
                self.add_event(event)
            
            return len(draft_calendar.events)
        else:
            # Partial update mode: update existing events, add new ones
            synced_count = 0
            
            for event in draft_calendar.events:
                # Check if event exists in main calendar
                existing_event = self.get_event(event.id)
                if existing_event:
                    # Update existing event
                    existing_event.update(
                        title=event.title,
                        description=event.description,
                        scheduled_start=event.scheduled_start,
                        deadline=event.deadline,
                        duration=event.duration,
                        priority=event.priority,
                        status=event.status,
                        category=event.category,
                        location=event.location,
                        tags=event.tags,
                        metadata=event.metadata
                    )
                else:
                    # Add new event
                    self.add_event(event)
                synced_count += 1
            
            return synced_count

    def update_event(self, event_id: str, **kwargs) -> Optional[CalendarEvent]:
        """Update an event in the calendar.
        
        Args:
            event_id: The ID of the event to update
            **kwargs: The fields to update
            
        Returns:
            The updated event, or None if not found
        """
        for event in self.events:
            if event.id == event_id:
                event.update(**kwargs)
                self.updated_at = datetime.now()
                return event
        return None

    def get_event(self, event_id: str) -> Optional[CalendarEvent]:
        """Get an event by ID.
        
        Args:
            event_id: The ID of the event to get
            
        Returns:
            The event, or None if not found
        """
        for event in self.events:
            if event.id == event_id:
                return event
        return None

    # ========== Filter Methods ==========

    def get_events_by_date(self, target_date: date) -> List[CalendarEvent]:
        """Get events for a specific date.
        
        Args:
            target_date: The date to filter by
            
        Returns:
            List of events on the specified date
        """
        result = []
        for event in self.events:
            event_date = event.scheduled_start.date()
            if event_date == target_date:
                result.append(event)
        return result

    def get_events_by_date_range(self, start_date: date, end_date: date) -> List[CalendarEvent]:
        """Get events within a date range.
        
        Args:
            start_date: The start date of the range
            end_date: The end date of the range
            
        Returns:
            List of events within the specified range
        """
        result = []
        for event in self.events:
            event_date = event.scheduled_start.date()
            if start_date <= event_date <= end_date:
                result.append(event)
        return result

    def get_todos(self) -> List[CalendarEvent]:
        """Get all todo items (events with status not completed or cancelled).
        
        Returns:
            List of todo items
        """
        return [event for event in self.events 
                if event.status not in [EventStatus.COMPLETED, EventStatus.CANCELLED]]

    def get_completed_events(self) -> List[CalendarEvent]:
        """Get all completed events.
        
        Returns:
            List of completed events
        """
        return [event for event in self.events if event.status == EventStatus.COMPLETED]

    def get_events_by_priority(self, priority: Priority) -> List[CalendarEvent]:
        """Get events by priority.
        
        Args:
            priority: The priority to filter by
            
        Returns:
            List of events with the specified priority
        """
        return [event for event in self.events if event.priority == priority]
    # ========== Statistics Methods ==========

    def get_statistics(self) -> Dict[str, Any]:
        """Get calendar statistics.
        
        Returns:
            Dictionary with calendar statistics
        """
        total_events = len(self.events)
        todo_count = len(self.get_todos())
        completed_count = len(self.get_completed_events())
        
        # Calculate events by priority
        priority_counts = {}
        for priority in Priority:
            priority_counts[priority.name] = len(self.get_events_by_priority(priority))
        
        return {
            "total_events": total_events,
            "todo_count": todo_count,
            "completed_count": completed_count,
            "priority_distribution": priority_counts,
            "calendar_name": self.name,
            "last_updated": self.updated_at.isoformat()
        }


    # ========== Serialization Methods ==========

    def to_json(self) -> str:
        """Convert calendar to JSON string.
        
        Returns:
            JSON string representation of the calendar
        """
        import json
        return json.dumps(self.model_dump(), indent=2, default=str, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "Calendar":
        """Create calendar from JSON string.
        
        Args:
            json_str: JSON string representation of the calendar
            
        Returns:
            Calendar instance
        """
        import json
        data = json.loads(json_str)
        
        # Convert events
        if 'events' in data:
            data['events'] = [CalendarEvent(**event_data) for event_data in data['events']]
        
        # Convert timestamps
        for field in ['created_at', 'updated_at']:
            if field in data and data[field]:
                data[field] = datetime.fromisoformat(data[field])
        
        return cls(**data)

    # ========== Helper Methods ==========

    def clear_completed(self) -> int:
        """Remove all completed events.
        
        Returns:
            Number of events removed
        """
        initial_length = len(self.events)
        self.events = [event for event in self.events if event.status != EventStatus.COMPLETED]
        removed_count = initial_length - len(self.events)
        if removed_count > 0:
            self.updated_at = datetime.now()
        return removed_count

    def sort_events(self, key='scheduled_start', reverse=False) -> "Calendar":
        """Sort events by a specific key.
        
        Args:
            key: The key to sort by
            reverse: Whether to sort in reverse order
            
        Returns:
            Self for method chaining
        """
        if key == 'scheduled_start':
            self.events.sort(key=lambda e: e.scheduled_start, reverse=reverse)
        elif key == 'priority':
            self.events.sort(key=lambda e: e.priority.value if e.priority else 0, reverse=reverse)
        elif key == 'status':
            self.events.sort(key=lambda e: e.status.value if e.status else 0, reverse=reverse)
        return self