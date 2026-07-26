from __future__ import annotations

import json
import os
import sys
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4


_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}


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
        key = os.path.normcase(str(path.resolve()))
        with _LOCKS_GUARD:
            self._lock = _PATH_LOCKS.setdefault(key, threading.RLock())
        self._entries = self._read()

    def put(self, name: str, identity: ProcessIdentity, owner: str = "") -> None:
        with self._exclusive_write():
            self._entries = self._read()
            self._entries[name] = {**asdict(identity), "owner": owner}
            self._write()

    def remove(self, name: str) -> None:
        with self._exclusive_write():
            self._entries = self._read()
            self._entries.pop(name, None)
            self._write()

    def get(self, name: str) -> dict | None:
        with self._lock:
            self._entries = self._read()
            value = self._entries.get(name)
            return dict(value) if value else None

    def items(self):
        with self._lock:
            self._entries = self._read()
            return tuple((name, dict(value)) for name, value in self._entries.items())

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
        temporary = self.path.with_name(
            f"{self.path.stem}.{os.getpid()}.{uuid4().hex}.tmp"
        )
        try:
            temporary.write_text(json.dumps(self._entries, indent=2), encoding="utf-8")
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    @contextmanager
    def _exclusive_write(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        with self._lock, lock_path.open("a+b") as lock_file:
            lock_file.seek(0)
            if lock_file.read(1) == b"":
                lock_file.write(b"0")
                lock_file.flush()
            lock_file.seek(0)
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
