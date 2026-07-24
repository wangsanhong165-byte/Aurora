"""SQLite-backed MemoryInterface implementation.

Wraps app.memory.store.MemoryStore, app.memory.ticker.MemoryTicker, and
app.memory.compiler to provide persistent memory for the Runtime pipeline.
Manages its own background ticker lifecycle — Runtime only calls start()/shutdown().
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.interfaces.memory import MemoryInterface

logger = logging.getLogger("sqlite-memory")


class SQLiteMemory(MemoryInterface):
    """MemoryInterface backed by SQLite (MemoryStore) + ticker + compiler.

    Stores conversation turns to the logs table and retrieves both
    facts and log entries. Also exposes compiled memory.md context.
    Falls back to in-memory list if SQLite init fails.

    Lifecycle:
        start() — opens the store, starts MemoryTicker, sets active character
        shutdown() — stops the ticker and memory store
    """

    def __init__(self):
        self._store: Any = None
        self._ticker: Any = None
        self._fallback: list[dict] = []
        self._character_registry: Any = None
        try:
            from app.memory.store import MemoryStore
            self._store = MemoryStore()
        except Exception as exc:
            logger.warning("SQLiteMemory init failed, using in-memory fallback: %s", exc)
            self._store = None

    def start(self, character_registry: Any = None, llm_provider: Any = None) -> None:
        """Initialize MemoryStore + MemoryTicker + character compiler context.

        Called once by Runtime after all providers are resolved.
        Parameters:
            character_registry: Character registry with active_id, on_activate.
            llm_provider: LLM interface provider (used to extract sync adapter
                          for the background ticker thread).
        """
        self._character_registry = character_registry
        from app.memory.store import memory_store
        from app.memory import (
            set_compiler_llm,
            set_active_char,
            on_character_switch as memory_on_switch,
        )

        # Ensure memory store is initialized
        memory_store.start()

        # Get sync LLM adapter for the ticker
        llm_adapter = self._get_ticker_adapter(llm_provider)
        if llm_adapter is not None:
            set_compiler_llm(llm_adapter)

        # Create and start the ticker
        from app.memory.ticker import MemoryTicker
        self._ticker = MemoryTicker(llm_adapter)
        self._ticker.start()

        # Set initial character in compiler
        if character_registry is not None:
            cid = getattr(character_registry, "active_id", None)
            if cid:
                set_active_char(cid)
                if llm_adapter is not None:
                    from app.memory.compiler import regenerate_for_character
                    regenerate_for_character(cid)

            # Register character switch callback
            if hasattr(character_registry, "on_activate"):
                character_registry.on_activate(
                    lambda old_id, new_id: memory_on_switch(old_id, new_id)
                )

    def shutdown(self) -> None:
        """Stop ticker and memory store gracefully."""
        if self._ticker is not None:
            self._ticker.stop(wait=False)
            self._ticker = None
        from app.memory.store import memory_store
        memory_store.stop(wait=False)

    def notify_turn(self) -> None:
        """Forward turn notification to the ticker (if running)."""
        if self._ticker is not None:
            self._ticker.notify_turn()

    @staticmethod
    def _get_ticker_adapter(llm_provider: Any) -> Any:
        """Extract or create a sync LLM adapter for the background ticker thread.

        The ticker runs in a daemon thread and needs a synchronous adapter with
        generate_text(). Priority:
          1. Reuse the LLM provider's internal sync adapter if available
          2. Create a standalone OpenAILLMAdapter if API key is configured
          3. Return None (ticker skips LLM-dependent work)
        """
        # Try to extract sync adapter from the LLM provider
        if llm_provider is not None:
            adapter = getattr(llm_provider, "_adapter", None)
            if adapter is not None and hasattr(adapter, "generate_text"):
                return adapter

        # Fallback: create standalone adapter from env config
        api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if api_key:
            try:
                from app.models.http_adapters import OpenAILLMAdapter
                return OpenAILLMAdapter()
            except Exception:
                return None
        return None

    async def store(self, event_type: str, data: dict) -> None:
        if self._store is not None:
            if event_type == "conversation_turn":
                user_text = data.get("user", "")
                assistant_text = data.get("assistant", "")
                if user_text or assistant_text:
                    reply = {"reply_text": assistant_text, "intent": data.get("intent", "conversation")}
                    from app.memory.compiler import get_active_char_id
                    char_id = data.get("character_id", get_active_char_id() or "default")
                    self._store.log_turn(user_text, reply, character_id=char_id)
        else:
            self._fallback.append({"event_type": event_type, "data": data})

    async def retrieve(
        self, query: str, limit: int = 10, *,
        character_id: str = "", event_type: str = "",
        input_origin: str = "user",
    ) -> list[dict]:
        results: list[dict] = []

        if self._store is not None:
            # 1. Facts from SQLite
            facts = self._store.search_facts(query=query, k=limit // 2)
            for f in facts:
                results.append({
                    "type": "fact",
                    "data": {"fact": f.get("fact", ""), "tags": f.get("tags", [])},
                    "source": "sqlite",
                })

            # 2. Log entries from SQLite
            logs = self._store.search_logs(query, limit=limit)
            for l in logs:
                results.append({
                    "type": "log",
                    "data": {"content": l.get("content", ""), "role": l.get("role", "")},
                    "source": "sqlite",
                })

            # 3. Compiled memory context (if available)
            from app.memory.compiler import get_compiled_memory
            compiled = get_compiled_memory(character_id)
            if compiled:
                results.append({
                    "type": "compiled",
                    "data": {"content": compiled[:1500]},
                    "source": "compiler",
                })
        else:
            # Fallback: return recent entries from in-memory list
            for entry in self._fallback[-limit:]:
                results.append({
                    "type": "memory",
                    "data": entry.get("data", {}),
                    "source": "fallback",
                })

        return results

    async def consolidate(self) -> None:
        if self._store is not None:
            self._store.rebuild_index()

    async def summarize(self, since: str) -> str:
        from app.memory.compiler import get_compiled_memory
        compiled = get_compiled_memory()
        if compiled:
            return compiled[:2000]
        if self._fallback:
            return f"{len(self._fallback)} events in memory."
        return "No compiled memory available."

    async def forget(self, before: str) -> int:
        if self._store is None:
            return 0
        try:
            total = 0
            total += self._store.delete_logs_before(before)
            total += self._store.delete_facts_before(before)
            return total
        except Exception:
            return 0
