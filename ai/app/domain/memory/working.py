"""Working memory — recent interaction scratchpad with attention decay.

Working memory holds the most recent N interactions in a structured form,
with attention weights that decay over time. It is NOT persisted — it is
rebuilt each session from conversation history.
"""

import time
from typing import Any


_SLOT_KEYS = {"role", "content", "timestamp", "attention", "type"}


class WorkingMemory:
    """Short-term working memory with attention decay.

    Working memory sits between raw conversation history and long-term
    episodic memory. It tracks recent interactions with attention weights
    so the most salient/recent items are prioritized for prompt context.

    Not persisted — rebuilt each session.
    """

    def __init__(self, max_slots: int = 15):
        self._slots: list[dict[str, Any]] = []
        self.max_slots = max_slots

    def push(self, role: str, content: str,
             slot_type: str = "conversation", **extra) -> None:
        """Add a new item to working memory with full attention."""
        slot = {
            "role": role,
            "content": content,
            "timestamp": time.time(),
            "attention": 1.0,
            "type": slot_type,
        }
        slot.update(extra)
        self._slots.append(slot)
        if len(self._slots) > self.max_slots:
            self._slots.pop(0)

    def recent(self, n: int = 5) -> list[dict]:
        """Return the n most recent items."""
        return self._slots[-n:]

    def decay(self, rate: float = 0.05) -> None:
        """Reduce attention for all items. Items below threshold are removed."""
        remaining = []
        for slot in self._slots:
            slot["attention"] = max(0.0, slot["attention"] - rate)
            if slot["attention"] > 0.1:
                remaining.append(slot)
        self._slots = remaining

    def get_attention_top(self, n: int = 5) -> list[dict]:
        """Return n items with highest attention."""
        sorted_slots = sorted(
            self._slots, key=lambda s: s["attention"], reverse=True
        )
        return sorted_slots[:n]

    def to_prompt_context(self, n: int = 5) -> str:
        """Format recent working memory as a prompt context string."""
        items = self.recent(n)
        if not items:
            return ""
        lines = ["[Recent context]"]
        for item in items:
            prefix = "You" if item["role"] == "assistant" else "User"
            lines.append(f"  {prefix}: {item['content'][:200]}")
        return "\n".join(lines)

    def clear(self) -> None:
        self._slots.clear()

    @property
    def count(self) -> int:
        return len(self._slots)

    def to_dict(self) -> dict:
        return {
            "max_slots": self.max_slots,
            "count": len(self._slots),
            "slots": self._slots[-10:],
        }
