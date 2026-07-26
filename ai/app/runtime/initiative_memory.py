"""Select high-value memory topics for proactive conversation."""

from __future__ import annotations

import time
from typing import Any


class InitiativeMemorySelector:
    def __init__(self, store: Any, cooldown_seconds: float = 21600):
        self.store = store
        self.cooldown_seconds = cooldown_seconds

    def select(self, character_id: str) -> dict | None:
        now = time.time()
        priority = (
            ("open_loop", "unfinished_topic"),
            ("recent_state", "recent_user_state"),
            ("episode", "shared_experience"),
            ("preference", "known_preference"),
        )
        for memory_type, reason in priority:
            memories = self.store.list_memories(
                character_id=character_id, memory_type=memory_type,
                active_only=True, limit=10,
            )
            for memory in memories:
                if now - self.store.initiative_last_used(
                    character_id, memory.get("id")
                ) < self.cooldown_seconds:
                    continue
                if float(memory.get("confidence", 0)) < 0.65:
                    continue
                return {
                    "topic": memory.get("content", ""),
                    "reason": reason,
                    "memory_id": memory.get("id"),
                    "importance": memory.get("importance", 0.5),
                }
        return None
