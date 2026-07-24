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
    input_origin: str = "user"
    user_text: str = ""
    reply_text: str = ""
    reasoning: str = ""
    segments: list = field(default_factory=list)
    emotion: str = "neutral"
    emotion_intensity: float = 0.5
    audio: bytes = b""
    # Presentation intent produced by the runtime. Transport maps this to the
    # active Live2D model without exposing renderer details to pipeline steps.
    live2d_intent: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    status_message: str = ""
    status_callback: Any = None
