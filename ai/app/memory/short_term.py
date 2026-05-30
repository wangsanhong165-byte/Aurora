"""Short-term conversation memory — JSONL-based rolling window."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ShortTermMemory:
    """Manages recent conversation turns as JSONL."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (Path(__file__).resolve().parents[2] / "memory" / "short_term.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self, limit: int = 8) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows[-limit:] if limit else rows

    def append(self, user_text: str, reply: dict[str, Any]) -> None:
        record = {
            "created_at": utc_now(),
            "user": user_text,
            "assistant": reply.get("reply_text", ""),
            "intent": reply.get("intent", "unknown"),
            "memory": reply.get("memory", {}),
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def count(self) -> int:
        return len(self.load(limit=0))

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


