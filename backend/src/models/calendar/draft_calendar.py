"""DraftCalendar class for managing draft events."""
import json
import uuid
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from .calendar_event import CalendarEvent
from .enums import DirtyType


class DraftCalendar(BaseModel):
    """
    DraftCalendar class for managing draft events.

    All draft events are stored in one list and differentiated by
    event attributes (category, status, metadata) instead of container split.
    """

    id: str = Field(
        default_factory=lambda: f"draft_calendar_{uuid.uuid4().hex[:8]}",
        description="Unique draft calendar identifier"
    )
    
    events: List[CalendarEvent] = Field(
        default_factory=list,
        description="Unified list of draft events"
    )
    dirty: Optional[DirtyType] = Field(
        default=None, 
        description="Flag indicating if there are unsaved changes"
    )

    def add_event(self, event: CalendarEvent) -> CalendarEvent:
        """Add an event to the draft calendar.
        
        Args:
            event: The event to add
            
        Returns:
            The added event
        """
        self.events.append(event)
        return event

    def remove_event(self, event_id: str) -> bool:
        """Remove an event from the draft calendar.
        
        Args:
            event_id: The ID of the event to remove
            
        Returns:
            True if the event was removed, False otherwise
        """
        initial_length = len(self.events)
        self.events = [event for event in self.events if event.id != event_id]
        if len(self.events) < initial_length:
            return True
        return False

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

    def update_event_batch(self, events: List[CalendarEvent]) -> int:
        """Batch update events from a specific source.
        
        This method removes all existing events with the same source as the 
        provided events, then adds all the new events to unified events list.
        All events in the provided list must have the same source.
        
        Args:
            events: List of CalendarEvent objects to add. All events must 
                    have the same source.
                    
        Returns:
            Number of events added
            
        Raises:
            ValueError: If events have different sources
        """
        if not events:
            return 0
        
        first_source = events[0].source
        for event in events:
            if event.source != first_source:
                raise ValueError(
                    f"All events must have the same source. "
                    f"Expected {first_source.value}, got {event.source.value}"
                )
        
        # Remove existing events with the same source
        events_to_remove = [
            event.id for event in self.events
            if event.source == first_source
        ]
        for event_id in events_to_remove:
            self.remove_event(event_id)
        
        # Add new events
        for event in events:
            self.add_event(event)
        
        return len(events)

    def update_events(self, events: List[CalendarEvent]):
        """Update events in the draft calendar.
        
        Args:
            events: List of CalendarEvent objects to update
        """

    # ------------------------------------------------------------------
    # JSON serialisation
    # ------------------------------------------------------------------

    def to_json(self) -> str:
        """Serialize this DraftCalendar to a JSON string."""
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "DraftCalendar":
        """Deserialize a DraftCalendar from a JSON string."""
        return cls(**json.loads(json_str))

    def to_json_file(self, path: Path) -> None:
        """Serialize this DraftCalendar to a JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.to_json())

    @classmethod
    def from_json_file(cls, path: Path) -> Optional["DraftCalendar"]:
        """Deserialize a DraftCalendar from a JSON file.

        Returns None if the file does not exist or is corrupted.
        """
        if not path.exists():
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return cls.from_json(f.read())
        except Exception:
            return None
        self.events = list(events)

    def clear_events(self):
        """Clear all events from the draft calendar."""
        self.events = []