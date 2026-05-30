"""Lightweight event bus with queue for UI polling."""

from __future__ import annotations

import queue
from collections import defaultdict
from typing import Any, Callable

Listener = Callable[[str, Any], None]


class EventBus:
    def __init__(self) -> None:
        self._listeners: dict[str, list[Listener]] = defaultdict(list)
        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue()

    def on(self, event_type: str, callback: Listener) -> None:
        self._listeners[event_type].append(callback)

    def emit(self, event_type: str, data: Any = None) -> None:
        # Notify direct listeners
        for cb in self._listeners.get(event_type, []):
            try:
                cb(event_type, data)
            except Exception as exc:
                print(f"[EventBus] Listener error for '{event_type}': {exc}")
        # Also push to pollable queue (for UI)
        self._queue.put((event_type, data))

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
