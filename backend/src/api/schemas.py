from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field


class CalendarEventResponse(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    source: str
    scheduled_start: str
    deadline: str
    duration: Optional[int] = None
    computed_end_time: Optional[str] = None
    location: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    category: str = "unknown"
    color_tag: str = "blue"
    recurring_rule: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    duration_minutes: int = 0
    is_feasible: bool = True
    is_overdue: bool = False
    is_recurring: bool = False


class CalendarResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    events: List[CalendarEventResponse] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DraftCalendarResponse(BaseModel):
    id: str
    events: List[CalendarEventResponse] = Field(default_factory=list)
    dirty: Optional[str] = None


class CreateEventRequest(BaseModel):
    title: str
    source: str = "personal"
    scheduled_start: str
    deadline: str
    duration: Optional[int] = None
    description: Optional[str] = None
    location: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None
    color_tag: str = "blue"
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UpdateEventRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    scheduled_start: Optional[str] = None
    deadline: Optional[str] = None
    duration: Optional[int] = None
    location: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None
    color_tag: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class ChatRequest(BaseModel):
    message: str


class CommitResponse(BaseModel):
    ok: bool = True
    synced_count: int = 0


class ResetDraftResponse(BaseModel):
    ok: bool = True
    reset_count: int = 0


class CalendarDiffResponse(BaseModel):
    new_events: List[Dict[str, Any]] = Field(default_factory=list)
    modified_events: List[Dict[str, Any]] = Field(default_factory=list)
    deleted_events: List[Dict[str, Any]] = Field(default_factory=list)
