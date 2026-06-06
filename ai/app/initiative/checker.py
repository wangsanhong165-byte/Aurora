"""Initiative checker: polls the initiative queue and decides whether to speak."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from app.core.event_bus import bus
from app.core.events import EventType
from app.core.state import state_store
from app.initiative.queue import InitiativeQueue


# Global singleton
initiative_queue = InitiativeQueue()


class InitiativeChecker:
    """Background timer that drains the initiative queue and asks Brain.

    Event sources (screen monitor, timer, state changes) push InitiativeEvent
    objects into the queue. This checker drains them periodically and calls
    a user-provided handler when the agent should speak.
    """

    def __init__(
        self,
        interval: float = 10.0,
        idle_threshold: float = 300.0,
    ) -> None:
        self.interval = interval
        self.idle_threshold = idle_threshold
        self._timer: threading.Timer | None = None
        self._running = False
        self._last_interaction = time.time()
        self.on_initiative: Callable[[list[Any]], None] | None = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._schedule()

    def stop(self) -> None:
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def touch(self) -> None:
        """Mark user interaction, reset idle timer."""
        self._last_interaction = time.time()

    def _schedule(self) -> None:
        if not self._running:
            return
        self._timer = threading.Timer(self.interval, self._tick)
        self._timer.daemon = True
        self._timer.start()

    def _tick(self) -> None:
        if not self._running:
            return
        try:
            self._check()
        finally:
            self._schedule()

    def _check(self) -> None:
        """Drain the queue and decide if agent should speak."""
        events = initiative_queue.drain(limit=10)

        # Auto-generate idle event if user has been inactive
        idle = time.time() - self._last_interaction
        if idle >= self.idle_threshold and not events:
            from app.initiative.queue import InitiativeEvent
            events.append(InitiativeEvent(
                type="idle_timeout",
                payload={"idle_seconds": idle},
                priority=1,
            ))

        if not events:
            return

        state = state_store.snapshot()
        activity = state.get("activity", "idle")
        attention = state.get("attention", "available")

        # Suppress if user is focused and events are low-priority
        max_priority = max((e.priority for e in events), default=0)
        if attention == "focused" and max_priority < 5:
            return
        if activity == "sleeping":
            return

        bus.publish(
            EventType.STATE_CHANGED,
            {"initiative_events": len(events), "max_priority": max_priority},
            source="initiative",
        )

        if self.on_initiative:
            self.on_initiative(events)
