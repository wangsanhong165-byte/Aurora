"""Bounded tool execution with timeout, safe retry, and audit metadata."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolExecutionResult:
    text: str
    audit: dict[str, Any]


class ToolExecutionSupervisor:
    def __init__(self, timeout_seconds: float = 20.0, read_only_attempts: int = 2):
        self.timeout_seconds = max(0.05, float(timeout_seconds))
        self.read_only_attempts = max(1, min(3, int(read_only_attempts)))

    async def execute(self, provider, name: str, args: dict, risk: str) -> ToolExecutionResult:
        attempts = self.read_only_attempts if risk == "read_only" else 1
        started = time.monotonic()
        status = "error"
        text = ""
        used_attempts = 0
        for attempt in range(1, attempts + 1):
            used_attempts = attempt
            try:
                text = await asyncio.wait_for(
                    provider.execute(name, args),
                    timeout=self.timeout_seconds,
                )
                status = "ok"
                break
            except asyncio.TimeoutError:
                status = "timeout"
                text = json.dumps({
                    "error": "tool_timeout", "tool": name,
                    "timeout_seconds": self.timeout_seconds,
                }, ensure_ascii=False)
            except Exception as exc:
                status = "error"
                text = json.dumps({
                    "error": "tool_failed", "tool": name, "message": str(exc),
                }, ensure_ascii=False)

        audit = {
            "tool": name,
            "risk": risk,
            "status": status,
            "attempts": used_attempts,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "argument_keys": sorted(str(key) for key in args),
        }
        return ToolExecutionResult(str(text), audit)
