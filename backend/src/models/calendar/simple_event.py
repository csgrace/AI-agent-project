from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from pydantic import BaseModel, Field, field_validator, model_validator, model_serializer
import uuid
from .enums import EventCategory, EventSource, Priority, EventStatus, ColorTag
from .recurring_rules import RecurringRule

class SimpleEvent(BaseModel):
    """
    Simple event model for basic information.
    """
    # ========== Basic Information ==========
    id: str = Field(
        default_factory=lambda: f"event_{uuid.uuid4().hex[:8]}",
        description="Unique event identifier"
    )
    title: str = Field(..., min_length=1, max_length=500, description="Event title")
    description: Optional[str] = Field(None, max_length=2000, description="Event description")
    start_time: datetime = Field(..., description="Event start time")
    end_time: datetime = Field(..., description="Event end time")
    duration: timedelta = Field(..., description="Event duration")
    category: EventCategory = Field(..., description="Event category")
    priority: Optional[Priority] = Field(None, description="Event priority")
    color_tag: Optional[ColorTag] = Field(None, description="Color tag for event")
    location: Optional[str] = Field(None, max_length=500, description="Event location")
    recurring_rule: Optional[RecurringRule] = Field(None, description="Recurrence rules")
    
    @field_validator('end_time')
    @classmethod
    def validate_end_time(cls, v: datetime, info) -> datetime:
        """Ensure end_time is after start_time."""
        start_time = info.data.get('start_time')
        if start_time and v <= start_time:
            raise ValueError('end_time must be after start_time')
        return v
    
    @property
    def duration_minutes(self) -> int:
        """Calculate event duration in minutes."""
        return int(self.duration.total_seconds() / 60)