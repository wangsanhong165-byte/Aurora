"""Semantic memory — facts, knowledge, and compiled memory context.

Semantic memory stores and retrieves factual knowledge about the user
and the world. It wraps the fact extraction and compilation system
with a clean domain API.
"""

from __future__ import annotations

from typing import Any


class SemanticMemory:
    """Domain-level semantic memory over stored facts and compiled context.

    Facts are character-independent (shared across characters).
    Compiled memory is per-character (today/week/longterm/facts sections).
    """

    def __init__(self, store: Any = None):
        """Optional store: SQLiteMemory or MemoryStore. Falls back gracefully."""
        self._store = store

    async def store_fact(self, fact: str, tags: list[str] | None = None,
                         source: str = "", importance: float = 0.5) -> None:
        """Persist a semantic fact."""
        if self._store is not None and hasattr(self._store, "_store"):
            inner = self._store._store
            if inner is not None and hasattr(inner, "add_fact"):
                inner.add_fact(fact, tags or [], source=source,
                               importance=importance)

    async def recall(self, query: str, k: int = 5) -> list[dict]:
        """Retrieve semantic facts relevant to a query."""
        if self._store is not None and hasattr(self._store, "retrieve"):
            results = await self._store.retrieve(query, limit=k)
            return [r for r in results if r.get("type") == "fact"]
        return []

    async def get_compiled(self, character_id: str = "") -> str:
        """Get the compiled memory.md for a character."""
        if self._store is not None:
            summary = await self._store.summarize("")
            if summary and summary != "No memories.":
                return summary
        return ""

    async def all_facts(self) -> list[dict]:
        """Get all stored facts."""
        if self._store is not None and hasattr(self._store, "_store"):
            inner = self._store._store
            if inner is not None and hasattr(inner, "get_all_facts"):
                return inner.get_all_facts()
        return []
