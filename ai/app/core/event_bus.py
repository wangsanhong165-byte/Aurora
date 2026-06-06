"""Lightweight event bus with queue for UI polling.

The bus keeps backward compatibility with the original ``emit(type, data)``
API, while also accepting structured ``Event`` envelopes for the companion
runtime architecture.
"""

from __future__ import annotations

import queue
from collections import defaultdict
from typing import Any, Callable

from app.core.events import Event

Listener = Callable[[str, Any], None]


class EventBus:
    def __init__(self) -> None:
        self._listeners: dict[str, list[Listener]] = defaultdict(list)
        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue()

    def on(self, event_type: str, callback: Listener) -> None:
        self._listeners[event_type].append(callback)

    def subscribe(self, event_type: str, callback: Listener) -> None:
        self.on(event_type, callback)

    def emit(self, event_type: str, data: Any = None) -> None:
        # Notify direct listeners
        for cb in self._listeners.get(event_type, []):
            try:
                cb(event_type, data)
            except Exception as exc:
                print(f"[EventBus] Listener error for '{event_type}': {exc}")
        # Also push to pollable queue (for UI)
        self._queue.put((event_type, data))

    def publish(self, event: Event | str, data: Any = None, source: str = "system") -> Event:
        if isinstance(event, Event):
            envelope = event
        else:
            payload = data if isinstance(data, dict) else {"value": data}
            envelope = Event.from_payload(event, payload, source=source)
        self.emit(envelope.type, envelope.to_dict())
        return envelope

    def drain(self) -> list[tuple[str, Any]]:
        """Drain all queued events (non-blocking). Used by UI polling."""
        events: list[tuple[str, Any]] = []
        while True:
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return events

    def clear(self) -> None:
        self._listeners.clear()
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break


bus = EventBus()
