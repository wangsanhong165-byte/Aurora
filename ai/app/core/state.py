"""Global state machine states for the voice agent."""

from enum import Enum, auto


class InputState(Enum):
    IDLE = auto()
    LISTENING = auto()
    RECORDING = auto()
    PROCESSING = auto()
    SPEAKING = auto()
