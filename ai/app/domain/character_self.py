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

    def sync_from_character(self) -> None:
        """Adopt direct domain changes made by learning or other providers."""
        self._state = deepcopy(self.character.dynamic_state())

    def stage(self, updates: dict[str, Any]) -> CharacterSelfChange:
        candidate = self.snapshot()
        candidate.update(deepcopy(updates))
        return CharacterSelfChange(state=candidate)

    def commit(self, change: CharacterSelfChange) -> None:
        self.character.restore_dynamic_state(deepcopy(change.state))
        self._state = deepcopy(change.state)

    def commit_emotion(self, emotion: str, *, intensity: float) -> None:
        """Commit immediate emotion and its slow mood effect atomically."""
        self.sync_from_character()
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

    def record_interaction(
        self,
        user_text: str,
        *,
        learned: list[dict[str, Any]] | None = None,
        previous_state: dict[str, Any] | None = None,
    ) -> None:
        """Record only observable, recent interaction context for the user view."""
        state = deepcopy(self.character.dynamic_state())
        text = " ".join(str(user_text or "").split())[:160]
        if text:
            focus = [f"刚刚聊到：{text}"]
            state["last_interaction"] = text
        else:
            focus = []
            state["last_interaction"] = ""

        previous = previous_state or {}
        previous_emotion = str((previous.get("emotion") or {}).get("current", ""))
        current_emotion = str((state.get("emotion") or {}).get("current", ""))
        changes = [str(item) for item in state.get("recent_changes", []) if str(item).strip()]
        if previous_emotion and current_emotion and previous_emotion != current_emotion:
            changes.insert(0, f"表达从{previous_emotion}变为{current_emotion}")
        for item in learned or []:
            content = str(item.get("content", "")).strip()
            if content:
                changes.insert(0, f"记住了：{content[:120]}")

        state["recent_focus"] = focus[:6]
        state["recent_changes"] = changes[:6]
        state["last_interaction_at"] = time.time()
        state["interaction_count"] = int(state.get("interaction_count", 0) or 0) + 1
        self.commit(CharacterSelfChange(state=state))
