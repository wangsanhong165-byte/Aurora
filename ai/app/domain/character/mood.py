"""Character mood — long-term emotional trends."""

import time
from typing import Any


class MoodTrend:
    """Long-term mood trend for the character.

    Unlike EmotionState (immediate reaction to events), MoodTrend tracks
    a slower-moving baseline that shifts gradually based on accumulated
    emotional history. Mood influences reply style, initiative likelihood,
    and expression defaults.
    """

    VALID_MOODS = frozenset({
        "neutral", "bright", "melancholy", "energetic",
        "tired", "playful", "affectionate",
    })

    # Ordered list of moods from negative to positive valence
    _MOOD_SCALE = [
        "melancholy", "tired", "neutral", "playful", "bright",
    ]
    _EMOTION_TO_MOOD_SHIFT = {
        "happy": 0.3, "surprised": 0.2, "gentle": 0.1,
        "serious": -0.1, "worried": -0.2, "sad": -0.3,
        "angry": -0.3, "jealous": -0.4,
    }

    def __init__(self, initial: str = "neutral"):
        self._current = initial if initial in self.VALID_MOODS else "neutral"
        self._valence: float = 0.0  # -1.0 to 1.0 cumulative
        self._history: list[dict[str, Any]] = []

    @property
    def current(self) -> str:
        return self._current

    def set(self, mood: str, triggered_by: str = "") -> None:
        """Directly set the mood."""
        if mood not in self.VALID_MOODS:
            mood = "neutral"
        self._current = mood
        self._history.append({
            "mood": mood,
            "triggered_by": triggered_by or "manual",
            "valence": self._valence,
            "timestamp": time.time(),
        })

    def _valence_to_mood(self) -> str:
        """Map cumulative valence to a mood label."""
        if self._valence > 0.5:
            return "bright"
        if self._valence > 0.2:
            return "playful"
        if self._valence < -0.5:
            return "melancholy"
        if self._valence < -0.2:
            return "tired"
        return "neutral"

    def shift_from_emotion(self, emotion_name: str) -> None:
        """Apply the single canonical emotion-to-mood transition."""
        delta = self._EMOTION_TO_MOOD_SHIFT.get(emotion_name, 0.0)
        if delta == 0.0:
            self.decay(rate=0.02)
            return
        self._valence = max(-1.0, min(1.0, self._valence + delta * 0.15))
        new_mood = self._valence_to_mood()
        if new_mood != self._current:
            self._current = new_mood
            self._history.append({
                "mood": new_mood,
                "triggered_by": f"emotion_shift:{emotion_name}",
                "valence": self._valence,
                "timestamp": time.time(),
            })
            self._history = self._history[-20:]

    def decay(self, rate: float = 0.01) -> None:
        """Slowly drift character mood toward neutral."""
        if self._valence > 0:
            self._valence = max(0.0, self._valence - rate)
        elif self._valence < 0:
            self._valence = min(0.0, self._valence + rate)
        self._current = self._valence_to_mood()

    def to_dict(self) -> dict:
        return {
            "current": self._current,
            "valence": self._valence,
            "history": self._history[-20:],
        }
