"""Unified calendar event model for multi-source schedule integration."""
import random
from datetime import datetime
from random import Random
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo
from pydantic import BaseModel, Field, field_validator, model_validator, model_serializer
import uuid

from .enums import EventSource, Priority, EventStatus, ColorTag, EventCategory
from .recurring_rules import RecurringRule


CN_TZ = ZoneInfo("Asia/Shanghai")


class CalendarEvent(BaseModel):
    """
    Unified calendar event model that can represent events from all sources.
    """

    # ========== Basic Information ==========
    id: str = Field(
        default_factory=lambda: f"event_{uuid.uuid4().hex[:8]}",
        description="Unique event identifier"
    )
    title: str = Field(..., min_length=1, max_length=500, description="Event title")
    description: Optional[str] = Field(None, max_length=2000, description="Event description")

    # ========== Source Information ==========
    source: EventSource = Field(..., description="Source of the event")

    # ========== Time Information ==========
    scheduled_start: datetime = Field(..., description="Schedule start time (can be adjusted by LLM)")
    deadline: datetime = Field(..., description="Deadline (hard constraint)")
    duration: Optional[int] = Field(None, description="Event duration in minutes")

    # ========== Location ==========
    location: Optional[str] = Field(None, max_length=500, description="Event location")

    # ========== Status and Priority ==========
    priority: Optional[Priority] = Field(None, description="Event priority")
    status: Optional[EventStatus] = Field(None, description="Event status")
    category: EventCategory = Field(default=EventCategory.UNKNOWN, description="Event category")

    # ========== Recurrence ==========
    recurring_rule: Optional[RecurringRule] = Field(None, description="Recurrence rules")

    # ========== Visual Customization ==========
    color_tag: ColorTag = Field(default_factory=lambda:random.choice(list(ColorTag)), description="Color tag for event")

    # ========== Metadata ==========
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Source-specific metadata"
    )

    # ========== Additional Fields ==========
    tags: Optional[List[str]] = Field(default_factory=list, description="Tags for categorization")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    # ========== Field Validators ==========

    @staticmethod
    def _is_aware(dt: datetime) -> bool:
        return dt.tzinfo is not None and dt.utcoffset() is not None

    @classmethod
    def _to_cn_naive(cls, dt: datetime) -> datetime:
        if cls._is_aware(dt):
            return dt.astimezone(CN_TZ).replace(tzinfo=None)
        return dt

    @field_validator('scheduled_start', 'deadline', mode='before')
    @classmethod
    def normalize_datetime_to_cn_naive(cls, v):
        if isinstance(v, datetime):
            return cls._to_cn_naive(v)
        return v

    @field_validator('deadline')
    @classmethod
    def validate_deadline(cls, v: datetime, info) -> datetime:
        """Ensure deadline is after scheduled_start."""
        scheduled_start = info.data.get('scheduled_start')
        if scheduled_start:
            compare_deadline = v
            compare_start = scheduled_start
            if cls._is_aware(v) and not cls._is_aware(scheduled_start):
                compare_start = scheduled_start.replace(tzinfo=v.tzinfo)
            elif not cls._is_aware(v) and cls._is_aware(scheduled_start):
                compare_deadline = v.replace(tzinfo=scheduled_start.tzinfo)

            if compare_deadline <= compare_start:
                raise ValueError('deadline must be after scheduled_start')
        return v

    @field_validator('priority')
    @classmethod
    def auto_upgrade_priority(cls, v: Priority, info) -> Priority:
        """Automatically upgrade priority for urgent events."""
        deadline = info.data.get('deadline')
        if deadline:
            now = datetime.now(deadline.tzinfo) if cls._is_aware(deadline) else datetime.now()
            time_remaining = deadline - now
            # If deadline within 48 hours, auto upgrade to HIGH
            if time_remaining.total_seconds() <= 48 * 3600:
                if v == Priority.MEDIUM:
                    return Priority.HIGH
        return v

    # ========== Model Validators ==========

    @model_validator(mode='after')
    def validate_recurring_consistency(self) -> 'CalendarEvent':
        """Validate that recurring events have valid rules."""
        if self.is_recurring:
            if not self.recurring_rule:
                raise ValueError('Recurring events must have recurring_rule')
        return self

    # ========== Properties ==========

    @property
    def duration_minutes(self) -> int:
        """Calculate event duration in minutes."""
        if self.duration is not None:
            return int(self.duration)
        else:
            delta = self.deadline - self.scheduled_start
            return int(delta.total_seconds() / 60)

    @property
    def is_overdue(self) -> bool:
        """Check if event is overdue."""
        if self.status == EventStatus.COMPLETED:
            return False
        now = datetime.now(self.deadline.tzinfo) if self._is_aware(self.deadline) else datetime.now()
        return self.deadline < now

    @property
    def is_recurring(self) -> bool:
        """Check if event is recurring."""
        return self.recurring_rule is not None

    @property
    def computed_end_time(self) -> Optional[datetime]:
        """Calculate event end time based on scheduled start and duration."""
        if self.duration is not None:
            from datetime import timedelta
            return self.scheduled_start + timedelta(minutes=self.duration)
        return None

    @property
    def is_feasible(self) -> bool:
        """Check if the scheduled time is feasible before deadline."""
        if self.computed_end_time and self.deadline:
            return self.computed_end_time <= self.deadline
        return True

    # ========== Serialization Methods ==========

    @model_serializer
    def serialize_model(self) -> Dict[str, Any]:
        """Custom serialization for JSON output."""
        data = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "source": self.source.value,
            "scheduled_start": self.scheduled_start.isoformat(),
            "deadline": self.deadline.isoformat(),
            "duration": self.duration,
            "location": self.location,
            "priority": self.priority.value if self.priority else None,
            "status": self.status.value if self.status else None,
            "category": self.category.value,
            "recurring_rule": self.recurring_rule.model_dump() if self.recurring_rule else None,
            "color_tag": self.color_tag,
            "metadata": self.metadata,
            "tags": self.tags,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "duration_minutes": self.duration_minutes,
            "computed_end_time": self.computed_end_time.isoformat() if self.computed_end_time else None,
            "is_feasible": self.is_feasible,
            "is_overdue": self.is_overdue,
            "is_recurring": self.is_recurring
        }
        return data

    def to_json(self) -> str:
        """Convert event to JSON string."""
        import json
        return json.dumps(self.serialize_model(), indent=2, default=str)

    @classmethod
    def from_json(cls, json_str: str) -> "CalendarEvent":
        """Create event from JSON string."""
        import json
        data = json.loads(json_str)

        # Convert ISO format strings back to datetime
        for field in ['scheduled_start', 'deadline', 'created_at', 'updated_at']:
            if field in data and data[field]:
                data[field] = datetime.fromisoformat(data[field])

        # Convert enums
        if 'source' in data:
            data['source'] = EventSource(data['source'])
        if data.get('priority') is not None:
            data['priority'] = Priority(data['priority'])
        if data.get('status') is not None:
            data['status'] = EventStatus(data['status'])
        if data.get('category') is not None:
            data['category'] = EventCategory(data['category'])

        # Recreate recurring rule if exists
        if data.get('recurring_rule'):
            data['recurring_rule'] = RecurringRule(**data['recurring_rule'])

        return cls(**data)

    # ========== Helper Methods ==========

    def update(self, **kwargs) -> "CalendarEvent":
        """Update event fields and return self."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = datetime.now()
        return self

    def complete(self) -> "CalendarEvent":
        """Mark event as completed."""
        self.status = EventStatus.COMPLETED
        self.updated_at = datetime.now()
        return self

    def cancel(self) -> "CalendarEvent":
        """Cancel the event."""
        self.status = EventStatus.CANCELLED
        self.updated_at = datetime.now()
        return self

    def format_for_display(self) -> str:
        """Format event for user-friendly display."""
        priority_text = self.priority.value if self.priority else "unknown"
        status_text = self.status.value if self.status else "unknown"
        lines = [
            f"📅 {self.title}",
            f"   Time: {self.scheduled_start.strftime('%Y-%m-%d %H:%M')} - {self.deadline.strftime('%H:%M')}",
            f"   Source: {self.source.value} | Priority: {priority_text} | Status: {status_text} | Category: {self.category.value}",
        ]
        if self.duration:
            lines.append(f"   Duration: {self.duration} minutes")
        if self.computed_end_time:
            lines.append(f"   Computed End: {self.computed_end_time.strftime('%H:%M')}")
        if self.is_feasible:
            lines.append(f"   Feasibility: ✅ Feasible")
        else:
            lines.append(f"   Feasibility: ❌ Not feasible")
        if self.location:
            lines.append(f"   Location: {self.location}")
        if self.description:
            lines.append(f"   Description: {self.description[:100]}...")
        return "\n".join(lines)

    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }