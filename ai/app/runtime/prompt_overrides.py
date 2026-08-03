"""Per-character user-owned prompt overrides."""

from __future__ import annotations

import re
from pathlib import Path


class PromptOverrideStore:
    """Persist bounded prompt additions without modifying character packages."""

    MAX_CHARS = 12_000
    _CHARACTER_ID = re.compile(r"^[A-Za-z0-9_-]+$")

    def __init__(self, base_dir: Path | str):
        self._base_dir = Path(base_dir)

    def _path_for(self, character_id: str) -> Path:
        if not character_id or not self._CHARACTER_ID.fullmatch(character_id):
            raise ValueError("invalid character id")
        return self._base_dir / f"{character_id}.md"

    def get(self, character_id: str) -> str:
        path = self._path_for(character_id)
        try:
            return path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return ""

    def set(self, character_id: str, content: str) -> str:
        normalized = str(content).replace("\r\n", "\n").strip()
        if len(normalized) > self.MAX_CHARS:
            raise ValueError(f"prompt override exceeds {self.MAX_CHARS} characters")

        path = self._path_for(character_id)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(normalized, encoding="utf-8")
        temp_path.replace(path)
        return normalized
