"""Canonical V3 event envelope shared by every WebSocket message."""

from __future__ import annotations

import time
import uuid
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, model_validator

from contracts.v3.events import TURN_EVENT_TYPES


PROTOCOL_VERSION = "3.0"
SUPPORTED_VERSIONS = frozenset({PROTOCOL_VERSION})
CANONICAL_ENVELOPE_FIELDS = (
    "protocolVersion",
    "eventId",
    "eventType",
    "sessionId",
    "turnId",
    "sequence",
    "source",
    "timestamp",
    "payload",
)

EventSource = Literal["frontend", "runtime", "bridge", "lifecycle", "platform"]
PayloadT = TypeVar("PayloadT", bound=BaseModel)


class EnvelopeValidationError(ValueError):
    """Raised when an envelope fails protocol validation."""


class EventEnvelope(BaseModel, Generic[PayloadT]):
    """Internal snake_case model with a canonical camelCase wire representation."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    protocol_version: Literal["3.0"] = Field(default=PROTOCOL_VERSION, alias="protocolVersion")
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex}", alias="eventId", min_length=1)
    event_type: str = Field(alias="eventType", min_length=1)
    session_id: str = Field(alias="sessionId", min_length=1)
    turn_id: str | None = Field(default=None, alias="turnId")
    sequence: int = Field(default=1, ge=1)
    source: EventSource = "runtime"
    timestamp: float = Field(default_factory=time.time, gt=0)
    payload: PayloadT | dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_turn_id_for_turn_events(self) -> "EventEnvelope[PayloadT]":
        if self.event_type in TURN_EVENT_TYPES and not self.turn_id:
            raise ValueError(f"turnId is required for {self.event_type}")
        return self

    @property
    def type(self) -> str:
        """Temporary internal alias while V2 handlers are removed in later phases."""
        return self.event_type

    def to_dict(self) -> dict[str, JsonValue]:
        return self.model_dump(mode="json", by_alias=True, exclude_none=False)

    @classmethod
    def from_dict(cls, data: dict[str, JsonValue]) -> "EventEnvelope":
        missing = [field for field in CANONICAL_ENVELOPE_FIELDS if field not in data]
        if missing:
            raise EnvelopeValidationError(f"Missing canonical envelope fields: {', '.join(missing)}")
        try:
            return cls.model_validate(data)
        except ValidationError:
            raise


def validate_version(version: str) -> None:
    if version != PROTOCOL_VERSION:
        raise EnvelopeValidationError(
            f"Unsupported protocolVersion: {version}. Supported: {PROTOCOL_VERSION}"
        )


def validate_envelope(envelope: EventEnvelope) -> None:
    validate_version(envelope.protocol_version)
    EventEnvelope.model_validate(envelope.model_dump())


def error_envelope(
    code: str,
    message: str,
    *,
    event_id: str = "",
    session_id: str = "",
    turn_id: str = "",
    sequence: int = 1,
) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id or f"evt_{uuid.uuid4().hex}",
        event_type="protocol.error",
        session_id=session_id or "session-unbound",
        turn_id=turn_id or None,
        sequence=max(1, sequence),
        source="runtime",
        payload={"code": code, "message": message},
    )


class SequenceTracker:
    """Track the last accepted sequence independently for each session."""

    def __init__(self) -> None:
        self._last_sequence: dict[str, int] = {}

    def accept(self, session_id: str, sequence: int) -> bool:
        last = self._last_sequence.get(session_id, 0)
        if sequence > last:
            self._last_sequence[session_id] = sequence
            return True
        return False

    def reset(self, session_id: str = "") -> None:
        if session_id:
            self._last_sequence.pop(session_id, None)
        else:
            self._last_sequence.clear()


SYSTEM_EVENT_TYPES = frozenset({
    "session.open",
    "session.opened",
    "session.closed",
    "session.ping",
    "session.pong",
    "runtime.status",
    "runtime.ready",
    "runtime.degraded",
    "service.status",
    "configuration.updated",
    "protocol.error",
    "management.requested",
    "management.result",
    "management.failed",
    "telemetry.batch",
})
