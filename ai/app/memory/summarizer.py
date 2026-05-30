"""Conversation summarizer — compress history to save LLM tokens."""

import json
from typing import Any


class Summarizer:
    """Compresses long conversation history into a summary paragraph.

    Uses simple heuristics: extracts key facts from memory blocks
    and merges recent turns into a concise summary.
    Future: can call LLM for better summaries.
    """

    def __init__(self, max_turns: int = 50) -> None:
        self.max_turns = max_turns

    def summarize(self, history: list[dict[str, Any]]) -> str:
        """Generate a summary from conversation history.

        Args:
            history: List of {"user": "...", "assistant": "...", "memory": {...}} records.

        Returns:
            A concise text summary suitable for LLM context injection.
        """
        if not history:
            return ""

        facts: set[str] = set()
        topics: list[str] = []

        for record in history[-self.max_turns:]:
            mem = record.get("memory", {})
            if isinstance(mem, dict):
                for fact in mem.get("facts", []):
                    facts.add(str(fact))
                summary = mem.get("summary", "")
                if summary:
                    topics.append(str(summary))

        parts: list[str] = []
        if topics:
            parts.append("Recent topics: " + "; ".join(topics[-5:]))
        if facts:
            parts.append("Key facts: " + "; ".join(list(facts)[-10:]))

        return ". ".join(parts) if parts else ""

    def compress(self, history: list[dict[str, Any]], keep_recent: int = 5) -> list[dict[str, Any]]:
        """Compress history: keep recent N turns + prepend a summary.

        Returns a compact list suitable for LLM context.
        """
        if len(history) <= keep_recent:
            return history

        older = history[:-keep_recent]
        recent = history[-keep_recent:]
        summary = self.summarize(older)

        compressed = list(recent)
        if summary:
            compressed.insert(0, {"system_summary": summary})

        return compressed
