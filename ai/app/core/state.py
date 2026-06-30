"""Global state machine states and runtime state store.

Simplified: removed MentalState's curiosity/attachment dimensions,
removed batch accumulation. Just a simple mood tracker.
"""

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


class MoodTracker:
    """Simple mood tracker (0-100).
    
    Updated per turn from keyword signals in conversation.
    Slowly regresses toward baseline when no strong signals.
    """

    def __init__(self, baseline: float = 60.0) -> None:
        self.mood = baseline
        self._baseline = baseline

    # Positive/negative keyword lists (lightweight, no LLM needed)
    _POSITIVE = [
        "哈哈", "开心", "太棒", "真好", "喜欢", "谢谢", "cool", "great", "awesome",
        "nice", "love", "wonderful", "excellent", "good", "happy", "yeah", "yay",
        "太好了", "不错", "厉害", "牛", "好看", "好听", "好玩", "有趣", "好开心",
    ]
    _NEGATIVE = [
        "烦", "累", "难过", "生气", "讨厌", "糟糕", "sad", "angry", "bad",
        "terrible", "hate", "awful", "frustrated", "tired",
        "好累", "烦死了", "无语", "崩溃", "不想", "没意思", "无聊",
        "不好", "不行", "失败", "错了", "太难", "不舒服",
    ]

    def update(self, user_text: str, reply_text: str = "") -> None:
        """Update mood from one conversation turn."""
        combined = (user_text + " " + reply_text).lower()
        
        pos_hits = min(sum(1 for w in self._POSITIVE if w in combined), 3)
        neg_hits = min(sum(1 for w in self._NEGATIVE if w in combined), 3)
        
        delta = pos_hits * 2.0 - neg_hits * 3.0
        
        self.mood += delta
        
        # Baseline regression (slow pull toward center)
        self.mood += (self._baseline - self.mood) * 0.02
        
        # Clamp
        self.mood = max(0.0, min(100.0, self.mood))
    
    def to_dict(self) -> dict[str, float]:
        return {"mood": round(self.mood, 1)}
    
    def reset(self) -> None:
        self.mood = self._baseline


# Global singleton
mood_tracker = MoodTracker()


# StateStore is now shared via app.runtime.state_store — import above.
