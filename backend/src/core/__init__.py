"""Core module for shared state and utilities."""
from .global_state import (
    SKILL_REGISTRY,
    CALENDAR,
    OBJECT_STORE,
    get_skill_registry,
    get_calendar,
    set_calendar,
    get_draft_calendar,
    set_draft_calendar,
    get_object_store,
    set_object_store,
)
from .object_store import ObjectStore

__all__ = [
    "SKILL_REGISTRY",
    "CALENDAR",
    "OBJECT_STORE",
    "ObjectStore",
    "get_skill_registry",
    "get_calendar",
    "set_calendar",
    "get_draft_calendar",
    "set_draft_calendar",
    "get_object_store",
    "set_object_store",
]
