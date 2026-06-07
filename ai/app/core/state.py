"""Global state machine states and runtime state store."""

from __future__ import annotations

from collections import deque
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


@dataclass(slots=True)
class MentalState:
    """Continuously evolving mental state (0-100).

    Update rules:
    - mood:      baseline 60, auto-regresses, per-turn cap ±8
    - curiosity: 10-turn window average, per-turn cap ±5
    - attachment: diminishing-returns growth, per-turn cap ±2, slow idle decay
    - All values batch-update every 5 turns for inertia.
    """
    mood: float = 60.0
    curiosity: float = 50.0
    attachment: float = 30.0

    # Pending deltas (accumulate, apply every BATCH_SIZE turns)
    _pending: dict[str, float] = field(default_factory=lambda: {"mood": 0.0, "curiosity": 0.0, "attachment": 0.0})
    _turn_count: int = 0

    BASELINE_MOOD: float = 60.0
    BATCH_SIZE: int = 5

    # Caps per batch (since batch=5, these are 5x single-turn caps)
    MAX_MOOD_CHANGE: float = 8.0 * 5
    MAX_CURIOSITY_CHANGE: float = 5.0 * 5
    MAX_ATTACHMENT_CHANGE: float = 2.0 * 5

    # Curiosity sliding window
    _recent_signals: deque = field(default_factory=lambda: deque(maxlen=10))

    def accumulate(self, user_text: str, reply_text: str, idle_sec: float = 0.0) -> bool:
        """Compute deltas from one turn and accumulate. Returns True if batch ready."""
        delta = _compute_delta(user_text, reply_text, idle_sec, self._recent_signals)
        for key in self._pending:
            self._pending[key] += delta.get(key, 0.0)
        self._turn_count += 1

        if self._turn_count >= self.BATCH_SIZE:
            self._apply_batch()
            return True
        return False

    def _apply_batch(self) -> None:
        """Apply accumulated deltas with caps and baseline regression."""
        # mood: apply delta + baseline regression
        raw_mood = self._pending["mood"]
        raw_mood = max(-self.MAX_MOOD_CHANGE, min(raw_mood, self.MAX_MOOD_CHANGE))
        self.mood += raw_mood
        self.mood += (self.BASELINE_MOOD - self.mood) * 0.03 * self.BATCH_SIZE

        # curiosity: apply delta with cap
        raw_cur = self._pending["curiosity"]
        raw_cur = max(-self.MAX_CURIOSITY_CHANGE, min(raw_cur, self.MAX_CURIOSITY_CHANGE))
        self.curiosity += raw_cur

        # attachment: apply delta with cap
        raw_att = self._pending["attachment"]
        raw_att = max(-self.MAX_ATTACHMENT_CHANGE, min(raw_att, self.MAX_ATTACHMENT_CHANGE))
        self.attachment += raw_att

        # Clamp all
        self.mood = max(0.0, min(100.0, self.mood))
        self.curiosity = max(0.0, min(100.0, self.curiosity))
        self.attachment = max(0.0, min(100.0, self.attachment))

        # Reset
        self._pending = {"mood": 0.0, "curiosity": 0.0, "attachment": 0.0}
        self._turn_count = 0

    def force_flush(self) -> None:
        """Apply any pending deltas immediately (e.g. on shutdown)."""
        if self._turn_count > 0:
            self._apply_batch()

    def to_dict(self) -> dict[str, float]:
        return {
            "mood": round(self.mood, 1),
            "curiosity": round(self.curiosity, 1),
            "attachment": round(self.attachment, 1),
        }


# ---- delta computation ----

def _compute_delta(
    user_text: str,
    reply_text: str,
    idle_sec: float,
    recent_signals: deque,
) -> dict[str, float]:
    """Compute single-turn deltas. Returns small, stable values."""
    combined = (user_text + " " + reply_text).lower()
    user_len = len(user_text)
    reply_len = len(reply_text)

    # Track signals for curiosity window
    has_question = "?" in user_text or "?" in user_text
    has_new_topic = user_len > 40  # longer input ~ new topic
    recent_signals.append({"question": has_question, "new_topic": has_new_topic})

    delta: dict[str, float] = {}

    # ---- Mood: positive/negative word signals (mild) ----
    pos_words = ["哈哈", "谢谢", "开心", "厉害", "不错", "好", "great", "nice", "love", "happy"]
    neg_words = ["烦", "累", "困", "难过", "生气", "讨厌", "sad", "angry", "tired"]
    pos_hits = sum(1 for w in pos_words if w in combined)
    neg_hits = sum(1 for w in neg_words if w in combined)
    # Cap: at most 2 hits per category to prevent stacking
    pos_hits = min(pos_hits, 2)
    neg_hits = min(neg_hits, 2)
    delta["mood"] = pos_hits * 1.5 - neg_hits * 2.0 + (0.5 if reply_len > 80 else 0.0)

    # ---- Curiosity: 10-turn window ----
    if len(recent_signals) >= 3:
        q_ratio = sum(1 for s in recent_signals if s["question"]) / len(recent_signals)
        nt_ratio = sum(1 for s in recent_signals if s["new_topic"]) / len(recent_signals)
        delta["curiosity"] = q_ratio * 1.5 + nt_ratio * 1.0 - 0.8  # slight downward pressure
    else:
        delta["curiosity"] = 0.0

    # ---- Attachment: diminishing returns ----
    growth = 0.8 * (1 - mental_state.attachment / 100)  # normalized
    if user_len < 5:
        growth *= 0.3  # very short input, minimal growth
    delta["attachment"] = growth

    # Idle decay: ~0.3 per hour when away
    if idle_sec > 1800:  # 30 min
        decay = idle_sec / 3600 * 0.3
        delta["attachment"] -= decay

    return delta


# Global singletons
mental_state = MentalState()


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
