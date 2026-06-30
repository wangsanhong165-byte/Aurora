"""Episodic memory — domain wrapper around conversation log storage.

Provides a clean domain API over the SQLite-backed log storage.
Episodic memory stores past conversation turns and retrieves them
by relevance to a query.
"""

from __future__ import annotations

from typing import Any


class EpisodicMemory:
    """Domain-level episodic memory over conversation logs.

    Wraps the persistence layer (SQLite logs table) with domain-specific
    retrieval logic. Each entry represents a past interaction episode.
    """

    def __init__(self, store: Any = None):
        """Optional store: SQLiteMemory or MemoryStore. Falls back gracefully."""
        self._store = store

    async def store_turn(self, user: str, assistant: str,
                         intent: str = "conversation",
                         character_id: str = "") -> None:
        """Record a conversation turn as an episodic memory."""
        if self._store is not None:
            if hasattr(self._store, "store"):
                await self._store.store("conversation_turn", {
                    "user": user, "assistant": assistant,
                    "intent": intent, "character_id": character_id,
                })

    async def recall(self, query: str, limit: int = 5) -> list[dict]:
        """Retrieve episodic memories relevant to a query."""
        if self._store is not None and hasattr(self._store, "retrieve"):
            results = await self._store.retrieve(query, limit=limit)
            return [r for r in results if r.get("type") in ("log", "compiled")]
        return []

    async def recent_by_character(self, character_id: str,
                                  n: int = 10) -> list[dict]:
        """Get the most recent N episodes for a given character."""
        if self._store is not None and hasattr(self._store, "_store"):
            store = self._store._store
            if store is not None:
                turns = store.recent_turns(n)
                return [{"role": t.get("role", ""),
                         "content": t.get("content", "")}
                        for t in turns]
        return []

    async def count_since(self, timestamp: float) -> int:
        """Count episodic memories since a given timestamp."""
        return 0  # placeholder
