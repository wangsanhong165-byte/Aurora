"""Structured event definitions for the companion runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventType:
    USER_MESSAGE = "user_message"
    VOICE_INPUT = "voice_input"
    ASR_FINISHED = "asr_finished"
    BRAIN_STARTED = "brain_started"
    BRAIN_FINISHED = "brain_finished"
    ASSISTANT_SEGMENT = "assistant_segment"
    ASSISTANT_REPLY = "assistant_reply"
    TTS_REQUESTED = "tts_requested"
    TTS_READY = "tts_ready"
    PLAYBACK_STARTED = "playback_started"
    PLAYBACK_FINISHED = "playback_finished"
    MEMORY_APPEND_REQUESTED = "memory_append_requested"
    MEMORY_BACKGROUND_QUEUED = "memory_background_queued"
    MEMORY_BACKGROUND_FINISHED = "memory_background_finished"
    STATE_CHANGED = "state_changed"
    SERVICE_STATUS = "service_status"
    TOOL_CALL = "tool_call"
    TURN_COMPLETED = "turn_completed"
    LOG = "log"


@dataclass(slots=True)
class Event:
    """A small envelope for crossing module boundaries."""

    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "system"
    event_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "type": self.type,
            "source": self.source,
            "created_at": self.created_at,
            "payload": self.payload,
        }

    @classmethod
    def from_payload(
        cls,
        event_type: str,
        payload: dict[str, Any] | None = None,
        source: str = "system",
    ) -> "Event":
        return cls(type=event_type, payload=payload or {}, source=source)
