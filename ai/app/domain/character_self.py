"""Durable character-state aggregate with explicit commit semantics."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import time
from typing import Any


@dataclass(frozen=True)
class CharacterSelfChange:
    state: dict[str, Any]


class CharacterSelf:
    """Own durable persona state; turns may only stage, never mutate it."""

    def __init__(self, character: Any):
        self.character = character
        self.character_id = str(getattr(character, "id", ""))
        self._state = deepcopy(character.dynamic_state())

    def snapshot(self) -> dict[str, Any]:
        return deepcopy(self._state)

    def stage(self, updates: dict[str, Any]) -> CharacterSelfChange:
        candidate = self.snapshot()
        candidate.update(deepcopy(updates))
        return CharacterSelfChange(state=candidate)

    def commit(self, change: CharacterSelfChange) -> None:
        self.character.restore_dynamic_state(deepcopy(change.state))
        self._state = deepcopy(change.state)

    def commit_emotion(self, emotion: str, *, intensity: float) -> None:
        """Commit immediate emotion and its slow mood effect atomically."""
        state = self.snapshot()
        state["emotion"] = {
            "current": emotion,
            "intensity": max(0.0, min(1.0, float(intensity))),
        }
        mood = dict(state.get("mood", {}))
        valence = float(mood.get("valence", 0.0))
        shifts = {
            "happy": 0.3, "surprised": 0.2, "gentle": 0.1,
            "serious": -0.1, "worried": -0.2, "sad": -0.3,
            "angry": -0.3, "jealous": -0.4,
        }
        valence = max(-1.0, min(1.0, valence + shifts.get(emotion, 0.0) * 0.15))
        if valence > 0.5:
            current = "bright"
        elif valence > 0.2:
            current = "playful"
        elif valence < -0.5:
            current = "melancholy"
        elif valence < -0.2:
            current = "tired"
        else:
            current = "neutral"
        history = list(mood.get("history", []))
        if current != mood.get("current", "neutral"):
            history.append({
                "mood": current,
                "triggered_by": f"emotion_shift:{emotion}",
                "valence": valence,
                "timestamp": time.time(),
            })
        state["mood"] = {
            "current": current,
            "valence": valence,
            "history": history[-20:],
        }
        self.commit(CharacterSelfChange(state=state))
