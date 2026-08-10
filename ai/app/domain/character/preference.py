"""Character preferences — learned from interaction history."""

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class Preference:
    """A learned preference about a topic."""
    topic: str
    valence: float       # -1.0 to 1.0 (negative to positive)
    confidence: float    # 0.0 to 1.0 (how sure we are)
    last_updated: float

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "valence": self.valence,
            "confidence": self.confidence,
            "last_updated": self.last_updated,
        }


class PreferenceTracker:
    """Learned preferences about topics the user has discussed.

    Preferences are built over time as the character observes the user's
    reactions and statements. They influence reply style and initiative topics.
    """

    def __init__(self):
        self._preferences: dict[str, Preference] = {}

    def update(self, topic: str, delta_valence: float) -> None:
        """Update preference for a topic with a valence delta."""
        now = time.time()
        if topic in self._preferences:
            pref = self._preferences[topic]
            # Weighted average: new observation vs existing
            alpha = 0.3  # learning rate
            pref.valence = max(-1.0, min(1.0,
                pref.valence + alpha * (delta_valence - pref.valence)))
            pref.confidence = min(1.0, pref.confidence + 0.1)
            pref.last_updated = now
        else:
            self._preferences[topic] = Preference(
                topic=topic,
                valence=max(-1.0, min(1.0, delta_valence)),
                confidence=0.3,
                last_updated=now,
            )

    def set_explicit(self, topic: str, valence: float) -> None:
        """Record an explicit user statement as authoritative.

        Explicit "I like/dislike X" statements replace the previous valence;
        only weaker inferred observations should use ``update`` smoothing.
        """
        normalized = max(-1.0, min(1.0, float(valence)))
        existing = self._preferences.get(topic)
        confidence = max(0.85, existing.confidence if existing else 0.0)
        self._preferences[topic] = Preference(
            topic=topic,
            valence=normalized,
            confidence=confidence,
            last_updated=time.time(),
        )

    def get(self, topic: str) -> Preference | None:
        return self._preferences.get(topic)

    def top_liked(self, n: int = 5) -> list[Preference]:
        """Return the n most-liked preferences (highest valence * confidence)."""
        sorted_prefs = sorted(
            self._preferences.values(),
            key=lambda p: p.valence * p.confidence,
            reverse=True,
        )
        return sorted_prefs[:n]

    def top_disliked(self, n: int = 5) -> list[Preference]:
        """Return the n most-disliked preferences."""
        sorted_prefs = sorted(
            self._preferences.values(),
            key=lambda p: p.valence * p.confidence,
        )
        return sorted_prefs[:n]

    @property
    def count(self) -> int:
        return len(self._preferences)

    def to_dict(self) -> dict:
        return {
            topic: pref.to_dict()
            for topic, pref in self._preferences.items()
        }
