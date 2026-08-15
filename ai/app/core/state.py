"""Global runtime activity state; character mood belongs to CharacterSelf."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from app.core.state_store import state_store  # noqa: F401 — shared singleton


class InputState(Enum):
    IDLE = auto()
    LISTENING = auto()
    RECORDING = auto()
    PROCESSING = auto()
    SPEAKING = auto()


@dataclass(slots=True)
class RuntimeState:
    """Schema for legacy state keys. Not used for storage — kept for type hints."""
    activity: str = "idle"
    attention: str = "available"
    emotion: str = "neutral"
    device: str = "desktop"
    context: str = ""
    input_state: str = InputState.IDLE.name
    metadata: dict[str, Any] = field(default_factory=dict)


# StateStore is now shared via app.runtime.state_store — import above.
