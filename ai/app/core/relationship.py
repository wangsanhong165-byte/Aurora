"""Relationship Memory — Monika's long-term perception of the user.

Separate from episodic memory. Tracks four continuous dimensions:
- trust:        how much Monika trusts the user       (0-100)
- familiarity:  how well Monika knows the user        (0-100)
- respect:      how much Monika admires the user      (0-100)
- concern:      how much Monika cares about the user  (0-100)

Growth follows diminishing returns (harder to grow when already high).
Values decay very slowly during long idle periods (hours to days).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from threading import RLock
from typing import Any

from app.core.events import utc_now


class RelationshipMemory:
    """Monika's relationship with the user — grows slowly, decays slowly."""

    __slots__ = (
        "trust", "familiarity", "respect", "concern",
        "events", "max_events",
        "_last_interaction", "_lock",
    )

    def __init__(
        self,
        trust: float = 30.0,
        familiarity: float = 20.0,
        respect: float = 40.0,
        concern: float = 30.0,
    ) -> None:
        self.trust = trust
        self.familiarity = familiarity
        self.respect = respect
        self.concern = concern

        self.events: list[dict[str, Any]] = []
        self.max_events: int = 30

        self._last_interaction: float = time.time()
        self._lock = RLock()

    # ---- update ----------------------------------------------------------

    def update(self, user_text: str, reply_text: str) -> None:
        """Update all relationship dimensions from one conversation turn.

        Applies idle decay first (only if user was away > 30 min), then
        applies growth from the current interaction.
        """
        now = time.time()
        with self._lock:
            elapsed = now - self._last_interaction
            self._last_interaction = now

            # Idle decay — very slow, only for long absences
            if elapsed > 1800:  # 30 minutes
                hours = elapsed / 3600
                decay = min(hours * 0.08, 3.0)  # max ~3 points per long absence
                self.trust = max(0.0, self.trust - decay * 0.4)
                self.familiarity = max(0.0, self.familiarity - decay * 0.25)
                self.concern = max(0.0, self.concern - decay * 0.2)

            # Interaction quality: 0-1 based on turn length
            user_len = len(user_text)
            reply_len = len(reply_text)
            quality = min((user_len + reply_len) / 240, 1.0)

            # Growth — diminishing returns: higher current → smaller gain
            self.trust += _diminish(self.trust, quality * 0.35)
            self.familiarity += _diminish(self.familiarity, quality * 0.45)
            self.respect += _diminish(self.respect, quality * 0.20)
            self.concern += _diminish(self.concern, quality * 0.45)

            # Longer replies signal investment
            if reply_len > 120:
                self.trust += _diminish(self.trust, 0.15)
                self.familiarity += _diminish(self.familiarity, 0.20)

            # Clamp
            self.trust = min(100.0, max(0.0, self.trust))
            self.familiarity = min(100.0, max(0.0, self.familiarity))
            self.respect = min(100.0, max(0.0, self.respect))
            self.concern = min(100.0, max(0.0, self.concern))

    # ---- events ----------------------------------------------------------

    def add_event(self, summary: str, event_type: str = "interaction") -> None:
        """Record a significant relationship event (shared experience)."""
        with self._lock:
            self.events.append({
                "summary": summary,
                "type": event_type,
                "time": utc_now(),
            })
            if len(self.events) > self.max_events:
                self.events = self.events[-self.max_events:]

    def recent_events(self, n: int = 5) -> list[str]:
        """Return recent relationship event summaries."""
        with self._lock:
            return [e["summary"] for e in self.events[-n:]]

    # ---- serialization ---------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "trust": round(self.trust, 1),
                "familiarity": round(self.familiarity, 1),
                "respect": round(self.respect, 1),
                "concern": round(self.concern, 1),
                "events": [e["summary"] for e in self.events[-5:]],
            }

    def summary_text(self) -> str:
        """Human-readable summary for prompt injection."""
        d = self.to_dict()
        parts: list[str] = []
        for key, label in [
            ("trust", "信任"), ("familiarity", "熟悉"),
            ("respect", "尊重"), ("concern", "关心"),
        ]:
            val = d[key]
            if val >= 80:
                parts.append(f"{label}=很高")
            elif val >= 60:
                parts.append(f"{label}=较高")
            elif val >= 40:
                parts.append(f"{label}=中等")
            elif val >= 20:
                parts.append(f"{label}=较低")
            else:
                parts.append(f"{label}=低")

        lines = [f"[关系状态] {', '.join(parts)}"]
        if d["events"]:
            lines.append("[共同经历] " + "; ".join(d["events"]))
        return "\n".join(lines)

    def save(self, path: Path | None = None) -> None:
        """Persist relationship state to disk."""
        if path is None:
            path = Path(__file__).resolve().parents[2] / "memory" / "relationship.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            data = {
                "trust": self.trust,
                "familiarity": self.familiarity,
                "respect": self.respect,
                "concern": self.concern,
                "events": self.events,
                "last_interaction": self._last_interaction,
            }
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, path: Path | None = None) -> bool:
        """Load relationship state from disk. Returns True on success."""
        if path is None:
            path = Path(__file__).resolve().parents[2] / "memory" / "relationship.json"
        if not path.exists():
            return False
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                self.trust = float(data.get("trust", 30.0))
                self.familiarity = float(data.get("familiarity", 20.0))
                self.respect = float(data.get("respect", 40.0))
                self.concern = float(data.get("concern", 30.0))
                self.events = data.get("events", [])
                self._last_interaction = float(data.get("last_interaction", time.time()))
            return True
        except (json.JSONDecodeError, KeyError, ValueError):
            return False


# ---- helpers ----------------------------------------------------------

def _diminish(current: float, base_gain: float) -> float:
    """Diminishing returns formula: gain shrinks as current approaches 100.

    At current=20:  ~80% of base_gain
    At current=50:  ~50% of base_gain
    At current=80:  ~20% of base_gain
    At current=95:  ~5%  of base_gain
    """
    return base_gain * (1.0 - current / 100.0)


# Global singleton
relationship = RelationshipMemory()
