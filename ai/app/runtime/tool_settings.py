"""Persistent user controls for LLM tool availability."""

from __future__ import annotations

import json
from pathlib import Path


class ToolSettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path or (
            Path(__file__).resolve().parents[2] / "data" / "tool_settings.json"
        )
        self._settings = self._load()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text("utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def is_enabled(self, name: str) -> bool:
        return bool(self._settings.get(name, {}).get("enabled", True))

    def set_enabled(self, name: str, enabled: bool) -> None:
        self._settings.setdefault(name, {})["enabled"] = bool(enabled)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._settings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def snapshot(self) -> dict:
        return json.loads(json.dumps(self._settings))


tool_settings = ToolSettingsStore()
