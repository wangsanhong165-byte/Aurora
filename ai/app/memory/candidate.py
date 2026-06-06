"""Candidate memory  pending memory cards before merge into long-term.

Sits between Extractor and Merger in the memory pipeline. Cards accumulate
here until a batch threshold is reached, then get merged and persisted.
This prevents writing to LongTermMemory on every single turn.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.memory.long_term import MemoryCard


class CandidateMemory:
    """JSONL-backed buffer for pending memory cards.

    Usage:
        cand = CandidateMemory()
        cand.append(MemoryCard(type="fact", content="..."))
        if cand.should_flush(min_cards=5, max_age_sec=300):
            cards = cand.drain()
    """

    def __init__(self, path: Path | None = None, max_cards: int = 100) -> None:
        base = Path(__file__).resolve().parents[2]
        self.path = path or base / "memory" / "candidates.jsonl"
        self.max_cards = max_cards
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ---- append ----------------------------------------------------------
    def append(self, card: MemoryCard) -> None:
        """Add a single candidate card."""
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(card.to_dict(), ensure_ascii=False) + "\n")

    def extend(self, cards: list[MemoryCard]) -> None:
        """Add multiple candidate cards."""
        if not cards:
            return
        with self.path.open("a", encoding="utf-8") as f:
            for card in cards:
                f.write(json.dumps(card.to_dict(), ensure_ascii=False) + "\n")

    # ---- drain -----------------------------------------------------------
    def drain(self) -> list[MemoryCard]:
        """Read all candidates, clear the store, return as MemoryCard list."""
        cards = self._load_cards()
        # Clear by truncating
        with self.path.open("w", encoding="utf-8") as f:
            f.write("")
        return cards

    def peek(self) -> list[MemoryCard]:
        """Read candidates without clearing."""
        return self._load_cards()

    # ---- flush policy ----------------------------------------------------
    def should_flush(self, min_cards: int = 5, max_age_sec: float = 300.0) -> bool:
        """Check whether candidates should be merged.

        Returns True if:
        - Candidate count >= min_cards, OR
        - Oldest candidate is older than max_age_sec
        """
        cards = self._load_cards()
        if not cards:
            return False
        if len(cards) >= min_cards:
            return True

        # Check age of oldest candidate
        import time
        from app.core.events import utc_now
        try:
            oldest = min(
                (c.created_at for c in cards if c.created_at),
                default=None,
            )
            if oldest:
                from datetime import datetime, timezone
                oldest_dt = datetime.fromisoformat(oldest)
                age = (datetime.now(timezone.utc) - oldest_dt).total_seconds()
                return age >= max_age_sec
        except (ValueError, TypeError):
            pass

        return False

    @property
    def count(self) -> int:
        return len(self._load_cards())

    # ---- internal --------------------------------------------------------
    def _load_cards(self) -> list[MemoryCard]:
        if not self.path.exists():
            return []
        cards: list[MemoryCard] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    cards.append(MemoryCard(
                        type=data.get("type", "fact"),
                        content=data.get("content", ""),
                        importance=float(data.get("importance", 0.5)),
                        confidence=float(data.get("confidence", 0.7)),
                        source=data.get("source", "conversation"),
                        metadata=data.get("metadata", {}),
                        id=data.get("id", ""),
                        created_at=data.get("created_at", ""),
                        updated_at=data.get("updated_at", ""),
                    ))
                except (json.JSONDecodeError, KeyError):
                    continue
        return cards[:self.max_cards]

    def clear(self) -> None:
        with self.path.open("w", encoding="utf-8") as f:
            f.write("")
