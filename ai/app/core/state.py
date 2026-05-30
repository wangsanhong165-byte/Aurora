"""Global state machine states for the voice agent."""

from enum import Enum, auto


class InputState(Enum):
    IDLE = auto()
    LISTENING = auto()
    RECORDING = auto()
    CONTINUATION = auto()   # post-speech gap: wait for user to continue
    PROCESSING = auto()
    SPEAKING = auto()
