"""Coordinated orchestration for character create, update, and delete."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from app.character.catalog import CharacterCatalog


logger = logging.getLogger("character.lifecycle")


class CharacterLifecycle:
    """Keep role persistence, runtime reload, and owned-data cleanup together."""

    def __init__(
        self,
        *,
        catalog: CharacterCatalog,
        runtime: Any,
        active_character_id: Callable[[], str],
        switch_character: Callable[[str], dict[str, Any]],
        prompt_configs: Any,
        prompt_overrides: Any,
        memory_store: Callable[[], Any],
        delete_histories: Callable[[str], int],
        delete_compiled_data: Callable[[str], Any],
    ) -> None:
        self._catalog = catalog
        self._runtime = runtime
        self._active_character_id = active_character_id
        self._switch_character = switch_character
        self._prompt_configs = prompt_configs
        self._prompt_overrides = prompt_overrides
        self._memory_store = memory_store
        self._delete_histories = delete_histories
        self._delete_compiled_data = delete_compiled_data

    def create(self, specification: dict[str, Any]) -> dict[str, Any]:
        character = self._catalog.create(specification)
        self._refresh_registry()
        return character

    def update(
        self,
        character_id: str,
        changes: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        target = str(character_id or "").strip().lower()
        is_active = self._active_character_id() == target
        if is_active and not bool(getattr(self._runtime, "_runtime_idle", True)):
            raise RuntimeError("runtime is processing a turn")

        snapshot = self._catalog.snapshot(target)
        persisted = False
        try:
            updated = self._catalog.update(target, changes)
            persisted = True
            self._refresh_registry()
            if is_active:
                self._ensure_switched(target)
            return updated, is_active
        except Exception:
            if persisted:
                try:
                    self._catalog.restore(snapshot)
                    self._refresh_registry()
                except Exception:
                    logger.exception("Failed to roll back character update: %s", target)
            raise

    def delete(self, character_id: str) -> dict[str, Any]:
        target = str(character_id or "").strip().lower()
        ids = [str(item.get("id", "")) for item in self._catalog.list()]
        if target not in ids:
            raise KeyError(f"character not found: {target}")
        if len(ids) <= 1:
            raise ValueError("cannot delete the last character")

        fallback = next(item for item in ids if item != target)
        if self._active_character_id() == target:
            self._ensure_switched(fallback)

        deleted = self._catalog.delete(target)
        self._prompt_configs.delete(target)
        self._prompt_overrides.delete(target)
        store = self._memory_store()
        database_rows = store.delete_character_data(target) if store is not None else {}
        deleted_histories = self._delete_histories(target)
        self._delete_compiled_data(target)
        self._refresh_registry()

        conversations = getattr(self._runtime, "_conversations_by_character", None)
        if isinstance(conversations, dict):
            conversations.pop(target, None)
        return {
            "deleted_character_id": target,
            "active_character_id": self._active_character_id(),
            "fallback_character_id": deleted["fallback_character_id"],
            "database_rows": database_rows,
            "deleted_histories": deleted_histories,
            "shared_assets_preserved": True,
        }

    def _refresh_registry(self) -> None:
        registry = getattr(self._runtime, "_character_registry", None)
        if registry is not None and hasattr(registry, "refresh"):
            registry.refresh()

    def _ensure_switched(self, character_id: str) -> None:
        switched = self._switch_character(character_id)
        if "error" in switched:
            raise RuntimeError(str(switched["error"]))
