"""Long-term memory card storage.

Long-term memory is structured storage. Vector indexes can be rebuilt from it
later, but they are not the source of truth.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.events import utc_now


@dataclass(slots=True)
class MemoryCard:
    type: str
    content: str
    importance: float = 0.5
    confidence: float = 0.7
    source: str = "conversation"
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LongTermMemoryStore:
    """JSONL-backed memory-card store."""

    def __init__(self, path: Path | None = None, max_cards: int = 500) -> None:
        base = Path(__file__).resolve().parents[2]
        self.path = path or base / "memory" / "long_term.jsonl"
        self.max_cards = max_cards
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self, limit: int = 0) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows[-limit:] if limit else rows

    def append(self, card: MemoryCard) -> None:
        rows = self.load()
        rows.append(card.to_dict())
        if len(rows) > self.max_cards:
            _protected = {"episode", "relationship"}
            protected = [r for r in rows if r.get("type") in _protected]
            trimmable = [r for r in rows if r.get("type") not in _protected]
            trimmable = sorted(
                trimmable,
                key=lambda item: (float(item.get("importance", 0)), item.get("created_at", "")),
            )
            keep = min(self.max_cards - len(protected), len(trimmable))
            rows = protected + trimmable[-keep:] if keep > 0 else protected
        with self.path.open("w", encoding="utf-8") as file:
            for row in rows:
                file.write(json.dumps(row, ensure_ascii=False) + "\n")

    def search_recent(self, limit: int = 8) -> list[dict[str, Any]]:
        return self.load(limit=limit)
