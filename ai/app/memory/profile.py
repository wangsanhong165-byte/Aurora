"""User profile — name, preferences, tone, language."""

import json
from pathlib import Path
from typing import Any


DEFAULT_PROFILE = {
    "name": "",
    "language": "zh",
    "preferences": {
        "tone": "natural",
        "verbosity": "concise",
    },
    "context": {},
}


class Profile:
    """User identity and preferences."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (Path(__file__).resolve().parents[2] / "memory" / "profile.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return dict(DEFAULT_PROFILE)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            # Merge with defaults for missing keys
            merged = dict(DEFAULT_PROFILE)
            merged.update(data)
            return merged
        except (json.JSONDecodeError, OSError):
            return dict(DEFAULT_PROFILE)

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._save()

    @property
    def tone(self) -> str:
        return self._data.get("preferences", {}).get("tone", "natural")

    @property
    def language(self) -> str:
        return self._data.get("language", "zh")


