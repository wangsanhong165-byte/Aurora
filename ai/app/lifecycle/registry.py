from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    create_time: float
    executable: str
    command: tuple[str, ...]
    port: int


class ProcessRegistry:
    def __init__(self, path: Path):
        self.path = path
        self._entries = self._read()

    def put(self, name: str, identity: ProcessIdentity, owner: str = "") -> None:
        self._entries[name] = {**asdict(identity), "owner": owner}
        self._write()

    def remove(self, name: str) -> None:
        self._entries.pop(name, None)
        self._write()

    def get(self, name: str) -> dict | None:
        return self._entries.get(name)

    def items(self):
        return self._entries.items()

    def matches(self, name: str, actual: ProcessIdentity) -> bool:
        stored = self.get(name)
        if not stored:
            return False
        return (
            stored["pid"] == actual.pid
            and abs(stored["create_time"] - actual.create_time) < 0.01
            and stored["executable"].lower() == actual.executable.lower()
            and tuple(stored["command"]) == actual.command
            and stored["port"] == actual.port
        )

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._entries, indent=2), encoding="utf-8")
        temporary.replace(self.path)
