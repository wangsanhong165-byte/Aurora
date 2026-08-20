"""Coordinated orchestration for character create, update, and delete."""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

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
        pending_cleanup_path: Path | None = None,
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
        self._pending_cleanup_path = pending_cleanup_path

    def create(self, specification: dict[str, Any]) -> dict[str, Any]:
        target = str(specification.get("id", "")).strip().lower()
        if target:
            remaining, _results, _warnings = self._cleanup_owned_data(
                target,
                self._pending_steps(target),
            )
            if remaining:
                self._store_pending_steps(target, remaining)
                raise RuntimeError(
                    f"character {target} still has pending owned-data cleanup"
                )
            self._store_pending_steps(target, [])
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
        steps = [
            "prompt_config", "prompt_override", "memory", "histories",
            "compiled", "registry_refresh",
        ]
        remaining, cleanup_results, cleanup_warnings = self._cleanup_owned_data(
            target,
            steps,
        )
        self._store_pending_steps(target, remaining)

        conversations = getattr(self._runtime, "_conversations_by_character", None)
        if isinstance(conversations, dict):
            conversations.pop(target, None)
        return {
            "deleted_character_id": target,
            "active_character_id": self._active_character_id(),
            "fallback_character_id": deleted["fallback_character_id"],
            "database_rows": cleanup_results.get("memory", {}),
            "deleted_histories": cleanup_results.get("histories", 0),
            "cleanup_pending": bool(remaining),
            "cleanup_warnings": cleanup_warnings,
            "shared_assets_preserved": True,
        }

    def retry_pending_cleanups(self) -> dict[str, Any]:
        """Retry idempotent cleanup left after committed character deletion."""
        warnings: list[dict[str, str]] = []
        for target, entry in list(self._read_pending().items()):
            steps = list(entry.get("steps", [])) if isinstance(entry, dict) else []
            remaining, _results, failed = self._cleanup_owned_data(target, steps)
            self._store_pending_steps(target, remaining)
            warnings.extend({"character_id": target, **item} for item in failed)
        pending = sorted(self._read_pending())
        return {"pending": pending, "warnings": warnings}

    def _cleanup_owned_data(
        self,
        target: str,
        steps: list[str],
    ) -> tuple[list[str], dict[str, Any], list[dict[str, str]]]:
        def delete_memory() -> dict[str, int]:
            store = self._memory_store()
            return store.delete_character_data(target) if store is not None else {}

        actions: dict[str, Callable[[], Any]] = {
            "prompt_config": lambda: self._prompt_configs.delete(target),
            "prompt_override": lambda: self._prompt_overrides.delete(target),
            "memory": delete_memory,
            "histories": lambda: self._delete_histories(target),
            "compiled": lambda: self._delete_compiled_data(target),
            "registry_refresh": self._refresh_registry,
        }
        remaining: list[str] = []
        results: dict[str, Any] = {}
        warnings: list[dict[str, str]] = []
        for step in steps:
            action = actions.get(step)
            if action is None:
                continue
            try:
                results[step] = action()
            except Exception as exc:
                logger.exception(
                    "Character %s cleanup step failed: %s", target, step,
                )
                remaining.append(step)
                warnings.append({"step": step, "error": str(exc)})
        return remaining, results, warnings

    def _pending_steps(self, target: str) -> list[str]:
        return list(self._read_pending().get(target, {}).get("steps", []))

    def _store_pending_steps(self, target: str, steps: list[str]) -> None:
        if self._pending_cleanup_path is None:
            return
        pending = self._read_pending()
        if steps:
            pending[target] = {
                "steps": list(dict.fromkeys(steps)),
                "updated_at": time.time(),
            }
        else:
            pending.pop(target, None)
        self._write_pending(pending)

    def _read_pending(self) -> dict[str, Any]:
        path = self._pending_cleanup_path
        if path is None or not path.is_file():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write_pending(self, pending: dict[str, Any]) -> None:
        path = self._pending_cleanup_path
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.stem}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(pending, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _refresh_registry(self) -> None:
        registry = getattr(self._runtime, "_character_registry", None)
        if registry is not None and hasattr(registry, "refresh"):
            registry.refresh()

    def _ensure_switched(self, character_id: str) -> None:
        switched = self._switch_character(character_id)
        if "error" in switched:
            raise RuntimeError(str(switched["error"]))
