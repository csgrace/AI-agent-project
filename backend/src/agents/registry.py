"""Agent registry for managing multiple agent instances.

Provides thread-safe registration, lookup, and per-agent locking
to support concurrent agent access from different API endpoints.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass
class AgentEntry:
    """Internal container for a registered agent."""

    name: str
    instance: Any
    lock: threading.Lock = field(default_factory=threading.Lock)
    busy: bool = False


class AgentRegistry:
    """Global registry of agent instances with per-agent locking.

    Usage::

        # Eager registration — agent is ready immediately.
        AgentRegistry.register("scheduler", my_agent)

        # Lazy registration — factory is called on first get().
        AgentRegistry.register_factory("automation", lambda: AutomationAgent())

        # Acquire/release for mutually exclusive access.
        if AgentRegistry.acquire("scheduler"):
            try:
                agent = AgentRegistry.get("scheduler")
                # ... use agent ...
            finally:
                AgentRegistry.release("scheduler")
    """

    _agents: Dict[str, AgentEntry] = {}
    _factories: Dict[str, Callable[[], Any]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    @classmethod
    def register(cls, name: str, instance: Any) -> None:
        """Register an already-initialized agent instance (eager)."""
        cls._agents[name] = AgentEntry(name=name, instance=instance)

    @classmethod
    def register_factory(cls, name: str, factory: Callable[[], Any]) -> None:
        """Register a factory callable for lazy initialisation."""
        cls._factories[name] = factory

    @classmethod
    def unregister(cls, name: str) -> None:
        """Remove a previously registered agent or factory."""
        cls._agents.pop(name, None)
        cls._factories.pop(name, None)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    @classmethod
    def get(cls, name: str) -> Optional[Any]:
        """Return the agent instance for *name*, or ``None``.

        If the name was registered via ``register_factory`` and has not
        been instantiated yet, the factory is called once and the result
        is promoted to a full registration.
        """
        entry = cls._agents.get(name)
        if entry is not None:
            return entry.instance

        # Lazy initialisation from factory.
        factory = cls._factories.pop(name, None)
        if factory is not None:
            instance = factory()
        elif name in cls._factories:
            # Factory was re-registered between pop and here — keep it.
            instance = cls._factories[name]()
        else:
            return None

        cls.register(name, instance)
        return cls._agents[name].instance

    # ------------------------------------------------------------------
    # Concurrency control
    # ------------------------------------------------------------------

    @classmethod
    def acquire(cls, name: str) -> bool:
        """Try to acquire the per-agent lock (non-blocking).

        Returns ``True`` if the lock was acquired, ``False`` if the agent
        does not exist or is already busy.
        """
        entry = cls._agents.get(name)
        if entry is None:
            return False
        if not entry.lock.acquire(blocking=False):
            return False
        entry.busy = True
        return True

    @classmethod
    def release(cls, name: str) -> None:
        """Release the per-agent lock."""
        entry = cls._agents.get(name)
        if entry is not None:
            entry.busy = False
            try:
                entry.lock.release()
            except RuntimeError:
                pass  # lock was not held

    @classmethod
    def is_busy(cls, name: str) -> bool:
        entry = cls._agents.get(name)
        return entry.busy if entry else False

    @classmethod
    def is_initialized(cls, name: str) -> bool:
        """Return ``True`` if *name* has been registered (eager or lazy)."""
        return name in cls._agents

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @classmethod
    def list_agents(cls) -> list[str]:
        """Return the names of all registered agents."""
        return list(cls._agents.keys())

    @classmethod
    def list_factories(cls) -> list[str]:
        """Return the names of all registered factories."""
        return list(cls._factories.keys())
