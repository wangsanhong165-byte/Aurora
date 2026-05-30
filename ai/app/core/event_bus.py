"""Lightweight event bus for decoupled component communication."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

Listener = Callable[[str, Any], None]


class EventBus:
    def __init__(self) -> None:
        self._listeners: dict[str, list[Listener]] = defaultdict(list)

    def on(self, event_type: str, callback: Listener) -> None:
        self._listeners[event_type].append(callback)

    def emit(self, event_type: str, data: Any = None) -> None:
        for cb in self._listeners.get(event_type, []):
            try:
                cb(event_type, data)
            except Exception as exc:
                print(f"[EventBus] Listener error for '{event_type}': {exc}")

    def clear(self) -> None:
        self._listeners.clear()


# Singleton
bus = EventBus()
