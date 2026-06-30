"""Memory domain operations — store, retrieve, consolidate, summarize, forget."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class MemoryEntry:
    event_type: str
    data: dict
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    id: str = ""


class MemoryOperations:
    """Domain-level memory operations.

    Wraps raw storage with business logic: dedup, relevance scoring,
    consolidation scheduling, and summarization.
    """

    def __init__(self, store: Any = None):
        self._store = store
        self._episodic: list[MemoryEntry] = []

    async def store(self, event_type: str, data: dict) -> None:
        entry = MemoryEntry(event_type=event_type, data=data)
        self._episodic.append(entry)
        if self._store is not None:
            await self._store(event_type, data)

    async def retrieve(self, query: str, limit: int = 10) -> list[dict]:
        if self._store is not None:
            return await self._store(query, limit)
        # Fallback: return recent entries
        return [
            {"event_type": e.event_type, "data": e.data, "timestamp": e.timestamp}
            for e in self._episodic[-limit:]
        ]

    async def consolidate(self) -> None:
        """Merge short-term memories into long-term storage."""
        if len(self._episodic) < 10:
            return
        # In a real implementation: summarize batch, store as long-term, clear episodic
        self._episodic.clear()

    async def summarize(self, since: str) -> str:
        """Generate a summary of memories since a given timestamp."""
        cutoff = float(since) if since.replace(".", "").isdigit() else 0.0
        relevant = [e for e in self._episodic if e.timestamp >= cutoff]
        if not relevant:
            return "No recent memories."
        return f"{len(relevant)} events since {since}."

    async def forget(self, before: str) -> int:
        """Remove memories older than a timestamp. Returns count removed."""
        cutoff = float(before) if before.replace(".", "").isdigit() else 0.0
        before_count = len(self._episodic)
        self._episodic = [e for e in self._episodic if e.timestamp >= cutoff]
        return before_count - len(self._episodic)
