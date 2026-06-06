"""Global state machine states and runtime state store."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum, auto
from threading import RLock
from typing import Any


class InputState(Enum):
    IDLE = auto()
    LISTENING = auto()
    RECORDING = auto()
    PROCESSING = auto()
    SPEAKING = auto()


@dataclass(slots=True)
class RuntimeState:
    """Current companion state. This stores facts; it does not decide."""

    activity: str = "idle"
    attention: str = "available"
    emotion: str = "neutral"
    device: str = "desktop"
    context: str = ""
    input_state: str = InputState.IDLE.name
    metadata: dict[str, Any] = field(default_factory=dict)


class StateStore:
    """Thread-safe storage for the current runtime state."""

    def __init__(self) -> None:
        self._state = RuntimeState()
        self._lock = RLock()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self._state)

    def update(self, **changes: Any) -> dict[str, Any]:
        with self._lock:
            for key, value in changes.items():
                if hasattr(self._state, key):
                    setattr(self._state, key, value)
                else:
                    self._state.metadata[key] = value
            return asdict(self._state)


state_store = StateStore()
