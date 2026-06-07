"""Focus System — tracks recently discussed topics with decaying weights.

Used to boost memory retrieval for topics the user and Monika
have been discussing recently, making conversations feel continuous.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


class FocusStore:
    """Lightweight topic tracker with exponential decay.

    Usage:
        focus = FocusStore()
        focus.update(["TTS latency", "memory system"])
        focus.top(3)  # → ["TTS latency", "memory system"]
    """

    def __init__(self, decay: float = 0.85, max_topics: int = 20) -> None:
        self._topics: dict[str, float] = {}  # topic → weight
        self._decay = decay
        self._max_topics = max_topics

    def update(self, topics: list[str]) -> None:
        """Decay all existing topics, then boost new ones."""
        # Decay
        for t in list(self._topics):
            self._topics[t] *= self._decay
            if self._topics[t] < 0.1:
                del self._topics[t]
        # Boost new topics
        for t in topics:
            t = t.strip()
            if not t or len(t) < 2:
                continue
            self._topics[t] = self._topics.get(t, 0.5) + 1.0
        # Cap
        if len(self._topics) > self._max_topics:
            sorted_items = sorted(self._topics.items(), key=lambda x: x[1], reverse=True)
            self._topics = dict(sorted_items[:self._max_topics])

    def top(self, n: int = 5) -> list[str]:
        """Return top N topics with weight > 0.3."""
        items = sorted(self._topics.items(), key=lambda x: x[1], reverse=True)
        return [t for t, w in items if w > 0.3][:n]

    def boost_scores(
        self,
        results: list[dict[str, Any]],
        max_boost: float = 0.15,
    ) -> list[dict[str, Any]]:
        """Boost search result scores for cards matching focus topics.

        Cards whose content overlaps with currently active topics
        get a score bonus, pushing them higher in retrieval order.
        """
        active = set(self.top(10))
        if not active:
            return results

        for r in results:
            content = str(r.get("card", {}).get("content", "")).lower()
            # Count overlapping topic words
            hits = sum(1 for t in active if t.lower() in content)
            if hits > 0:
                boost = min(hits * 0.03, max_boost)
                r["score"] = round(r.get("score", 0) + boost, 4)

        # Re-sort
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return results

    @property
    def empty(self) -> bool:
        return len(self._topics) == 0

    def to_dict(self) -> dict[str, float]:
        return dict(self._topics)


# Global singleton
focus_store = FocusStore()
