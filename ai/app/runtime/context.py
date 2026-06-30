from dataclasses import dataclass, field
from typing import Any

from app.runtime.event import Event


@dataclass
class Context:
    """Shared context passed through Pipeline Steps.

    Each Step reads from and writes to context as the event flows
    through the pipeline.
    """
    event: Event
    state: dict = field(default_factory=dict)
    user_text: str = ""
    reply_text: str = ""
    segments: list = field(default_factory=list)
    emotion: str = "neutral"
    emotion_intensity: float = 0.5
    audio: bytes = b""
    error: str = ""
    status_message: str = ""
    status_callback: Any = None
