"""TurnTelemetry — non-blocking structured event tracking for all pipeline stages.

Telemetry is a write-only observer that never blocks or alters the main flow.
A failing observer must not cause the turn to fail.
Sensitive content (full prompts, user text) is excluded by default.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger("telemetry")


class TelemetryStage(str, Enum):
    """Canonical pipeline stages tracked by telemetry."""

    TURN_STARTED = "turn.started"
    TURN_COMPLETED = "turn.completed"
    TURN_FAILED = "turn.failed"
    TURN_CANCELLED = "turn.cancelled"

    ASR_STARTED = "asr.started"
    ASR_RESULT = "asr.result"

    MEMORY_RETRIEVE_STARTED = "memory.retrieve.started"
    MEMORY_RETRIEVE_COMPLETED = "memory.retrieve.completed"

    PROMPT_COMPOSED = "prompt.composed"

    LLM_STARTED = "llm.started"
    LLM_FIRST_TOKEN = "llm.first_token"
    LLM_COMPLETED = "llm.completed"

    TOOL_STARTED = "tool.started"
    TOOL_RESULT = "tool.result"

    INTENT_CREATED = "intent.created"

    TTS_STARTED = "tts.started"
    TTS_SEGMENT_READY = "tts.segment.ready"

    AUDIO_STARTED = "audio.started"
    AUDIO_COMPLETED = "audio.completed"

    CHARACTER_INTENT_SENT = "character.intent.sent"
    CHARACTER_INTENT_RECEIVED = "character.intent.received"

    ACTION_ENQUEUED = "action.enqueued"
    MOTION_STARTED = "motion.started"

    MEMORY_SAVE_STARTED = "memory.save.started"
    MEMORY_SAVE_COMPLETED = "memory.save.completed"

    LIVE2D_INTENT_CREATED = "live2d.intent.created"


class TelemetryStatus(str, Enum):
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class TurnTelemetryEvent:
    """One structured telemetry event for a pipeline stage."""

    session_id: str
    turn_id: str
    span_id: str
    parent_span_id: str
    stage: str
    status: str
    timestamp: float
    duration_ms: float | None = None
    error_code: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "stage": self.stage,
            "status": self.status,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "error_code": self.error_code,
            "metadata": dict(self.metadata),
        }


Observer = Callable[[TurnTelemetryEvent], None]


class TurnTelemetry:
    """Per-turn telemetry recorder. Non-blocking, write-only.

    Usage:
        telemetry = TurnTelemetry(session_id="ses_xxx", turn_id="turn_xxx")
        telemetry.record(TelemetryStage.LLM_STARTED)
        # ... do work ...
        telemetry.record(TelemetryStage.LLM_COMPLETED, status="ok", duration_ms=1234)
        telemetry.emit_all(observer)  # flush to observer(s)
    """

    def __init__(
        self,
        session_id: str = "",
        turn_id: str = "",
        parent_span_id: str = "",
    ):
        self.session_id = session_id
        self.turn_id = turn_id
        self.parent_span_id = parent_span_id
        self.events: list[TurnTelemetryEvent] = []
        self._timers: dict[str, float] = {}
        self._span_stack: list[str] = []

    @staticmethod
    def generate_id(prefix: str = "evt") -> str:
        return f"{prefix}_{uuid.uuid4().hex[:12]}"

    @staticmethod
    def generate_session_id() -> str:
        return f"ses_{uuid.uuid4().hex[:12]}"

    def start_span(self, stage: str) -> str:
        """Begin a new span for the given stage. Returns span_id."""
        span_id = self.generate_id("span")
        parent = self._span_stack[-1] if self._span_stack else self.parent_span_id
        self._span_stack.append(span_id)
        self._timers[span_id] = time.perf_counter()
        event = TurnTelemetryEvent(
            session_id=self.session_id,
            turn_id=self.turn_id,
            span_id=span_id,
            parent_span_id=parent,
            stage=stage,
            status=TelemetryStatus.OK,
            timestamp=time.time(),
        )
        self.events.append(event)
        return span_id

    def end_span(self, span_id: str, status: str = TelemetryStatus.OK, error_code: str | None = None, metadata: dict | None = None) -> None:
        """Complete a previously started span."""
        started = self._timers.pop(span_id, None)
        duration = (time.perf_counter() - started) * 1000 if started else None
        # Find and update the matching start event
        for event in reversed(self.events):
            if event.span_id == span_id and event.duration_ms is None:
                event.duration_ms = duration
                if status != TelemetryStatus.OK:
                    event.status = status
                if error_code:
                    event.error_code = error_code
                if metadata:
                    event.metadata.update(metadata)
                break
        if self._span_stack and self._span_stack[-1] == span_id:
            self._span_stack.pop()

    def record(self, stage: str, status: str = TelemetryStatus.OK, duration_ms: float | None = None, error_code: str | None = None, metadata: dict | None = None) -> str:
        """Record a single telemetry event (non-span). Returns event_id."""
        span_id = self.generate_id("span")
        event = TurnTelemetryEvent(
            session_id=self.session_id,
            turn_id=self.turn_id,
            span_id=span_id,
            parent_span_id=self._span_stack[-1] if self._span_stack else self.parent_span_id,
            stage=stage,
            status=status,
            timestamp=time.time(),
            duration_ms=duration_ms,
            error_code=error_code,
            metadata=metadata or {},
        )
        self.events.append(event)
        return span_id

    def fail(self, stage: str, error_code: str, message: str = "") -> str:
        """Convenience: record a failed stage."""
        return self.record(stage, status=TelemetryStatus.FAILED, error_code=error_code, metadata={"message": message} if message else None)

    def to_list(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.events]

    def emit_all(self, observer: Observer) -> None:
        """Flush all events to an observer.

        The observer must not raise (or its exceptions are caught and logged).
        """
        for event in self.events:
            try:
                observer(event)
            except Exception:
                logger.exception("Telemetry observer failed for stage %s", event.stage)

    def clear(self) -> None:
        self.events.clear()
        self._timers.clear()
        self._span_stack.clear()


# Module-level telemetry state (set once per process lifecycle)
_session_id: str = TurnTelemetry.generate_session_id()


def get_session_id() -> str:
    """Return the process-wide session ID."""
    return _session_id


def reset_session_id() -> str:
    """Generate a new session ID (e.g. after reconnection)."""
    global _session_id
    _session_id = TurnTelemetry.generate_session_id()
    return _session_id
