"""Memory adapter abstractions for uncertain memory backend integration."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol

from ...models.calendar.calendar_event import CalendarEvent


class MemoryProvider(Protocol):
    """Protocol for pluggable memory providers."""

    def query_context(self, event: CalendarEvent, top_k: int = 3) -> List[Dict[str, Any]]:
        """Return related memory items for an event."""


class NoOpMemoryProvider:
    """Default provider that returns no memory context."""

    def query_context(self, event: CalendarEvent, top_k: int = 3) -> List[Dict[str, Any]]:
        return []


class MemoryAdapter:
    """Adapter that isolates uncertainty in the memory implementation."""

    def __init__(self, provider: Optional[MemoryProvider] = None) -> None:
        self.provider = provider or NoOpMemoryProvider()

    def query_context(self, event: CalendarEvent, top_k: int = 3) -> List[Dict[str, Any]]:
        """Query memory context with graceful degradation on errors."""
        try:
            results = self.provider.query_context(event=event, top_k=top_k)
            return results or []
        except Exception as exc:
            print(f"Warning: memory query failed for event {event.id}: {exc}")
            return []
