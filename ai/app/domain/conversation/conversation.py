"""Conversation domain — turn tracking and history management."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Turn:
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    metadata: dict = field(default_factory=dict)


class Conversation:
    """A conversation session — ordered turns with context management.

    Manages turn history, context window limits, and provides the
    message list for LLM calls.
    """

    def __init__(self, max_turns: int = 50):
        self._turns: list[Turn] = []
        self._max_turns = max_turns

    def add_turn(self, role: str, content: str, **metadata) -> None:
        self._turns.append(Turn(role=role, content=content, metadata=metadata))
        if len(self._turns) > self._max_turns:
            self._turns.pop(0)

    def get_history(self, limit: int | None = None) -> list[dict[str, str]]:
        """Return history as message dicts for LLM consumption."""
        turns = self._turns[-limit:] if limit else self._turns
        return [{"role": t.role, "content": t.content} for t in turns]

    def clear(self) -> None:
        self._turns.clear()

    @property
    def turn_count(self) -> int:
        return len(self._turns)

    @property
    def last_turn(self) -> Turn | None:
        return self._turns[-1] if self._turns else None

    def to_dict(self) -> dict:
        return {
            "turn_count": self.turn_count,
            "turns": [
                {"role": t.role, "content": t.content[:100], "timestamp": t.timestamp}
                for t in self._turns[-10:]  # last 10 for preview
            ],
        }
