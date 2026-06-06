"""Project memory and decision storage."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.events import utc_now


@dataclass(slots=True)
class ProjectDecision:
    title: str
    reason: str = ""
    category: str = "architecture"
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProjectStore:
    """JSON-backed store for project state and decisions."""

    def __init__(self, path: Path | None = None) -> None:
        base = Path(__file__).resolve().parents[2]
        self.path = path or base / "memory" / "project_state.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"current": {}, "decisions": [], "todos": []}
        try:
            with self.path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (json.JSONDecodeError, OSError):
            return {"current": {}, "decisions": [], "todos": []}
        data.setdefault("current", {})
        data.setdefault("decisions", [])
        data.setdefault("todos", [])
        return data

    def save(self, data: dict[str, Any]) -> None:
        with self.path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

    def add_decision(self, title: str, reason: str = "", category: str = "architecture") -> dict[str, Any]:
        data = self.load()
        decision = ProjectDecision(title=title, reason=reason, category=category).to_dict()
        data["decisions"].append(decision)
        self.save(data)
        return decision

    def snapshot(self) -> dict[str, Any]:
        return self.load()
