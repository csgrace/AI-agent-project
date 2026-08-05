from datetime import datetime
import re
from typing import Optional, List, Dict, Any
from zoneinfo import ZoneInfo
from pydantic import BaseModel, Field, field_validator

from ...models.calendar.enums import EventSource, Priority, EventStatus, EventCategory


CN_TZ = ZoneInfo("Asia/Shanghai")


def _to_cn_naive(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None and dt.utcoffset() is not None:
        return dt.astimezone(CN_TZ).replace(tzinfo=None)
    return dt


class QueryCalendarParams(BaseModel):
    """参数模型：查询日历事件"""
    use_main_calendar: bool = Field(default=False, description="是否查询主日历：True=主日历，False=draft日历")
    detail_level: str = Field(default="summary", description="返回详细程度: summary 或 full")
    max_inline: int = Field(default=20, description="最大内联事件数")
    start_time: Optional[datetime] = Field(default=None, description="开始时间")
    end_time: Optional[datetime] = Field(default=None, description="结束时间")
    event_id: Optional[str] = Field(default=None, description="事件ID")
    source: Optional[EventSource] = Field(default=None, description="事件来源")
    category: Optional[EventCategory] = Field(default=None, description="事件类别")
    status: Optional[EventStatus] = Field(default=None, description="事件状态")
    title_keyword: Optional[str] = Field(default=None, description="标题关键字")

    @field_validator("start_time", "end_time", mode="after")
    @classmethod
    def normalize_query_datetimes(cls, v):
        return _to_cn_naive(v)


class CalendarEventCreate(BaseModel):
    """参数模型：创建日历事件"""
    title: str = Field(..., description="事件标题")
    source: EventSource = Field(..., description="事件来源")
    scheduled_start: datetime = Field(..., description="计划开始时间")
    deadline: datetime = Field(..., description="截止时间")
    duration: Optional[int] = Field(default=None, description="持续时间（分钟）")
    description: Optional[str] = Field(default=None, description="事件描述")
    priority: Optional[Priority] = Field(default=None, description="优先级")
    status: Optional[EventStatus] = Field(default=None, description="状态")
    category: Optional[EventCategory] = Field(default=None, description="类别")
    location: Optional[str] = Field(default=None, description="地点")
    tags: Optional[List[str]] = Field(default_factory=list, description="标签")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="元数据")

    @field_validator("scheduled_start", "deadline", mode="after")
    @classmethod
    def normalize_event_datetimes(cls, v):
        return _to_cn_naive(v)

    @field_validator("duration", mode="before")
    @classmethod
    def parse_duration(cls, v):
        if v is None or isinstance(v, int):
            return v
        if isinstance(v, float):
            return int(v)
        if isinstance(v, str):
            text = v.strip().lower()
            if text.isdigit():
                return int(text)

            match = re.search(r"(\d+(?:\.\d+)?)", text)
            if not match:
                return v

            number = float(match.group(1))
            if any(unit in text for unit in ["hour", "hours", "hr", "hrs", "h", "小时"]):
                return int(number * 60)
            if any(unit in text for unit in ["minute", "minutes", "min", "mins", "m", "分钟"]):
                return int(number)
            return int(number)
        return v

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source(cls, v):
        if isinstance(v, str):
            normalized = v.strip().lower()
            mapping = {
                "university": EventSource.UNIVERSITY,
                "blackboard": EventSource.BLACKBOARD,
                "personal": EventSource.PERSONAL,
            }
            if normalized in mapping:
                return mapping[normalized]
        return v

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(cls, v):
        if isinstance(v, str):
            normalized = v.strip().lower()
            mapping = {
                "high": Priority.HIGH,
                "medium": Priority.MEDIUM,
                "low": Priority.LOW,
            }
            if normalized in mapping:
                return mapping[normalized]
        return v

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v):
        if isinstance(v, str):
            normalized = v.strip().lower()
            mapping = {
                "pending": EventStatus.PENDING,
                "in_progress": EventStatus.IN_PROGRESS,
                "completed": EventStatus.COMPLETED,
                "cancelled": EventStatus.CANCELLED,
            }
            if normalized in mapping:
                return mapping[normalized]
        return v

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, v):
        if isinstance(v, str):
            normalized = v.strip().lower()
            mapping = {
                "background": EventCategory.BACKGROUND,
                "solid": EventCategory.SOLID,
                "schedulable": EventCategory.SCHEDULABLE,
                "ignored": EventCategory.IGNORED,
                "unknown": EventCategory.UNKNOWN,
            }
            if normalized in mapping:
                return mapping[normalized]
        return v


class AddCalendarEventParams(BaseModel):
    """参数模型：添加日历事件"""
    event: CalendarEventCreate = Field(..., description="事件信息")


class RemoveCalendarEventParams(BaseModel):
    """参数模型：删除日历事件"""
    event_id: str = Field(..., description="事件ID")


class CalendarEventUpdate(BaseModel):
    """参数模型：更新日历事件"""
    title: Optional[str] = Field(default=None, description="事件标题")
    description: Optional[str] = Field(default=None, description="事件描述")
    source: Optional[EventSource] = Field(default=None, description="事件来源")
    scheduled_start: Optional[datetime] = Field(default=None, description="计划开始时间")
    deadline: Optional[datetime] = Field(default=None, description="截止时间")
    duration: Optional[int] = Field(default=None, description="持续时间（分钟）")
    priority: Optional[Priority] = Field(default=None, description="优先级")
    status: Optional[EventStatus] = Field(default=None, description="状态")
    category: Optional[EventCategory] = Field(default=None, description="类别")
    location: Optional[str] = Field(default=None, description="地点")
    tags: Optional[List[str]] = Field(default=None, description="标签")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="元数据")

    @field_validator("scheduled_start", "deadline", mode="after")
    @classmethod
    def normalize_update_datetimes(cls, v):
        return _to_cn_naive(v)

    @field_validator("duration", mode="before")
    @classmethod
    def parse_duration(cls, v):
        return CalendarEventCreate.parse_duration(v)

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source(cls, v):
        return CalendarEventCreate.normalize_source(v)

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(cls, v):
        return CalendarEventCreate.normalize_priority(v)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v):
        return CalendarEventCreate.normalize_status(v)

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, v):
        return CalendarEventCreate.normalize_category(v)


class UpdateCalendarEventParams(BaseModel):
    """参数模型：更新日历事件"""
    event_id: str = Field(..., description="事件ID")
    updates: CalendarEventUpdate = Field(..., description="更新内容")
