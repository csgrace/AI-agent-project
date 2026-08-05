"""Tool for estimating event durations from ObjectStore keys."""
from __future__ import annotations

from typing import List, Optional

from langchain.tools import tool

from ...core.global_state import get_object_store
from ...models.calendar.calendar_event import CalendarEvent
from ..shared_utils.memory_adapter import MemoryAdapter
from .utils import estimate_event_durations


@tool
def estimate_event_durations_from_store(
    object_store_key: str,
    user_hint: Optional[str] = None,
    missing_only: bool = True,
) -> str:
    """Estimate event durations and return a new ObjectStore key.

    The tool reads an event list from ObjectStore, runs a per-event loop of
    memory query + LLM inference, fills duration in minutes (stored into
    `CalendarEvent.duration` as minutes), and writes the
    updated list into a new ObjectStore key.

    Args:
        object_store_key: Input key pointing to a `List[CalendarEvent]` item.
        user_hint: Optional user hint to improve LLM inference.
        missing_only: Whether to only fill events whose duration is missing.

    Returns:
        A new ObjectStore key that points to the updated event list.

    Raises:
        KeyError: If the input key does not exist in ObjectStore.
        TypeError: If the stored object is not a `List[CalendarEvent]`.
    """
    object_store = get_object_store()
    events: List[CalendarEvent] = object_store.get_typed(object_store_key, List[CalendarEvent])

    estimated_events = estimate_event_durations(
        events=events,
        memory_adapter=MemoryAdapter(),
        user_hint=user_hint,
        missing_only=missing_only,
    )

    output_key = object_store.put(
        estimated_events,
        metadata={
            "kind": "calendar_event_list",
            "generated_by": "estimate_event_durations_from_store",
            "source_key": object_store_key,
            "missing_only": missing_only,
        },
    )
    return output_key
