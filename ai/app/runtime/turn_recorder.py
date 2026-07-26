"""Persistent, sanitized, read-only CharacterTurn flight recorder."""

from __future__ import annotations

import json
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.runtime.character_turn import CharacterTurn


def _safe_text(value: Any, limit: int = 1200) -> str:
    return str(value or "").strip()[:limit]


def _redact_text(value: Any, limit: int = 1200) -> str:
    text = _safe_text(value, limit)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED_KEY]", text)
    text = re.sub(
        r"(?i)\b(bearer|api[_ -]?key|token)\s*[:=]\s*\S+",
        r"\1=[REDACTED]",
        text,
    )
    text = re.sub(r"[A-Za-z]:[\\/][^\s\"']+", "[REDACTED_PATH]", text)
    return text


def _memory_summary(item: Any) -> dict[str, str]:
    if not isinstance(item, dict):
        return {"summary": _safe_text(item, 300)}
    data = item.get("data") if isinstance(item.get("data"), dict) else item
    return {
        "type": _safe_text(item.get("type") or item.get("memory_type"), 40),
        "summary": _safe_text(data.get("content"), 300),
    }


class TurnRecorder:
    def __init__(
        self,
        path: Path | None = None,
        *,
        max_turns: int = 500,
        retention_days: int = 30,
    ):
        root = Path(__file__).resolve().parents[2]
        self.path = path or root / "data" / "runtime" / "turns.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_turns = max(1, int(max_turns))
        self.retention_days = max(1, int(retention_days))
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS turn_traces ("
                "turn_id TEXT PRIMARY KEY, created_at REAL NOT NULL, "
                "phase TEXT NOT NULL, origin TEXT NOT NULL, "
                "summary TEXT NOT NULL, detail_json TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_turn_traces_created "
                "ON turn_traces(created_at DESC)"
            )

    def record(self, turn: CharacterTurn) -> None:
        detail = self._project(turn)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO turn_traces"
                "(turn_id, created_at, phase, origin, summary, detail_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    turn.turn_id,
                    float(turn.created_at),
                    turn.phase.value,
                    turn.input_origin,
                    _safe_text(turn.user_text, 160),
                    json.dumps(detail, ensure_ascii=False),
                ),
            )
            self._cleanup(conn)

    def _cleanup(self, conn: sqlite3.Connection) -> None:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        ).timestamp()
        conn.execute("DELETE FROM turn_traces WHERE created_at < ?", (cutoff,))
        conn.execute(
            "DELETE FROM turn_traces WHERE turn_id IN ("
            "SELECT turn_id FROM turn_traces ORDER BY created_at DESC "
            "LIMIT -1 OFFSET ?)",
            (self.max_turns,),
        )

    def list_turns(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT turn_id, created_at, phase, origin, summary "
                "FROM turn_traces ORDER BY created_at DESC LIMIT ?",
                (max(1, min(200, int(limit))),),
            ).fetchall()
        return [{
            "turnId": row["turn_id"],
            "createdAt": datetime.fromtimestamp(
                row["created_at"], timezone.utc
            ).isoformat(),
            "phase": row["phase"],
            "origin": row["origin"],
            "summary": row["summary"],
        } for row in rows]

    def get_turn(self, turn_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT detail_json FROM turn_traces WHERE turn_id = ?",
                (str(turn_id),),
            ).fetchone()
        return json.loads(row["detail_json"]) if row else None

    def _project(self, turn: CharacterTurn) -> dict[str, Any]:
        plan = turn.output.performance
        step_events = []
        cursor = 0.0
        for name, duration in turn.metrics.items():
            if not name.endswith("_ms") or name == "e2e_latency_ms":
                continue
            value = max(0.0, float(duration))
            step_name = name.removesuffix("_ms")
            step_events.append({
                "event": {
                    "ASRStep": "ASR transcription",
                    "CharacterStep": "CharacterSelf snapshot",
                    "MemoryRetrieveStep": "Memory retrieve",
                    "DecisionStep": "Prompt compiled (redacted) and LLM response parsed",
                    "EmotionStep": "Character emotion committed",
                    "MemorySaveStep": "Memory commit",
                    "TTSStep": "TTS synthesis",
                    "Live2DStep": "PerformancePlan dispatched",
                }.get(step_name, step_name),
                "offsetMs": round(cursor, 2),
                "durationMs": round(value, 2),
                "timestamp": datetime.fromtimestamp(
                    turn.created_at + cursor / 1000, timezone.utc
                ).isoformat(),
            })
            cursor += value
        if turn.input.audio:
            step_events.insert(0, {
                "event": "ASR input received",
                "offsetMs": 0,
                "timestamp": datetime.fromtimestamp(
                    turn.created_at, timezone.utc
                ).isoformat(),
            })
        step_events.append({
            "event": (
                f"CharacterIntent: {plan.emotion} / "
                f"{plan.behavior or 'idle'} / attention={plan.attention}"
            ),
            "offsetMs": round(cursor, 2),
            "timestamp": datetime.fromtimestamp(
                turn.created_at + cursor / 1000, timezone.utc
            ).isoformat(),
        })
        if turn.output.audio:
            step_events.extend([
                {
                    "event": "TTS started; lip sync enabled",
                    "offsetMs": round(cursor, 2),
                    "timestamp": datetime.fromtimestamp(
                        turn.created_at + cursor / 1000, timezone.utc
                    ).isoformat(),
                },
                {
                    "event": "TTS ended; return to idle",
                    "offsetMs": round(cursor, 2),
                    "timestamp": datetime.fromtimestamp(
                        turn.created_at + cursor / 1000, timezone.utc
                    ).isoformat(),
                },
            ])
        return {
            "turnId": turn.turn_id,
            "readOnly": True,
            "createdAt": datetime.fromtimestamp(
                turn.created_at, timezone.utc
            ).isoformat(),
            "phase": turn.phase.value,
            "origin": turn.input_origin,
            "input": {"text": _safe_text(turn.user_text, 600)},
            "response": {
                "text": _safe_text(turn.reply_text),
                "segments": [
                    {
                        "text": _safe_text(item.get("text"), 300),
                        "tone": _safe_text(item.get("tone"), 40),
                        "gesture": _safe_text(item.get("gesture"), 40),
                    }
                    for item in turn.segments
                    if isinstance(item, dict)
                ][:20],
            },
            "performance": {
                "emotion": _safe_text(plan.emotion, 40),
                "behavior": _safe_text(plan.behavior, 40),
                "attention": _safe_text(plan.attention, 40),
                "intensity": max(0.0, min(1.0, float(plan.energy))),
                "speaking": bool(plan.speaking),
                "durationMs": plan.duration_ms,
            },
            "memory": {
                "retrieved": [_memory_summary(item) for item in turn.memories[:20]],
                "committed": [_memory_summary(item) for item in turn.learned_memories[:20]],
            },
            "tools": [
                {
                    "tool": _safe_text(item.get("tool") or item.get("name"), 80),
                    "approved": bool(item.get(
                        "approved", item.get("status") != "denied"
                    )),
                    "status": _safe_text(item.get("status"), 40),
                }
                for item in turn.tool_audit[:20]
                if isinstance(item, dict)
            ],
            "prompt": {
                "view": "redacted",
                "contextBudget": {
                    key: value for key, value in turn.context_budget.items()
                    if key in {"estimated_tokens", "max_tokens", "truncated"}
                },
            },
            "usage": {
                key: value for key, value in turn.llm_usage.items()
                if key in {
                    "prompt_tokens", "completion_tokens", "total_tokens",
                    "cached_tokens", "model", "estimated_cost_usd",
                }
            },
            "timeline": step_events,
            "warnings": [_redact_text(item, 200) for item in turn.warnings[:20]],
            "error": (
                {
                    "code": _safe_text(turn.error.code, 80),
                    "message": _redact_text(turn.error.message, 300),
                    "retryable": bool(turn.error.retryable),
                }
                if turn.error else None
            ),
            "retention": {
                "days": self.retention_days,
                "maximumTurns": self.max_turns,
            },
        }


_default_recorder: TurnRecorder | None = None


def get_turn_recorder() -> TurnRecorder:
    global _default_recorder
    if _default_recorder is None:
        _default_recorder = TurnRecorder()
    return _default_recorder
