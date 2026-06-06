"""Initiative queue.

Event sources place proactive opportunities here. Brain decides whether to
speak; event sources never call an LLM directly.
"""

from __future__ import annotations

import queue
from dataclasses import dataclass, field
from typing import Any

from app.core.events import utc_now


@dataclass(slots=True)
class InitiativeEvent:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    priority: int = 0


class InitiativeQueue:
    def __init__(self) -> None:
        self._queue: queue.Queue[InitiativeEvent] = queue.Queue()

    def push(self, event_type: str, payload: dict[str, Any] | None = None, priority: int = 0) -> None:
        self._queue.put(InitiativeEvent(type=event_type, payload=payload or {}, priority=priority))

    def drain(self, limit: int = 20) -> list[InitiativeEvent]:
        events: list[InitiativeEvent] = []
        while len(events) < limit:
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return sorted(events, key=lambda event: event.priority, reverse=True)
