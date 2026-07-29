"""V3 Protocol Envelope — unified event wrapper for all WebSocket messages.

Every message that crosses the WebSocket boundary is wrapped in an EventEnvelope.
The payload is a discriminated union keyed by `type`.

Unknown types must be reported as error("unsupported_event"), never silently ignored.
Unknown protocol_version must be reported as error("unsupported_protocol_version").
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


# ── Protocol versioning ──────────────────────────────────────────────────

PROTOCOL_VERSION = "3.0"
SUPPORTED_VERSIONS = {"3.0"}

# Legacy protocol versions that the compat layer can convert from
LEGACY_VERSIONS = {"2.0"}


# ── Envelope ─────────────────────────────────────────────────────────────

@dataclass
class EventEnvelope:
    """Unified envelope wrapping every WebSocket message.

    Fields:
        protocol_version: Semantic version string (e.g. "3.0").
        event_id: Globally unique event identifier (e.g. "evt_abc123").
        session_id: Process/session-wide identifier (e.g. "ses_abc123").
        turn_id: Per-turn identifier (e.g. "turn_abc123").
        sequence: Monotonically increasing sequence per sender. Used for
                  ordering and duplicate detection.
        timestamp: Unix timestamp (seconds since epoch).
        source: Logical source component ("runtime" | "bridge" | "frontend" |
                "lifecycle").
        type: Discriminated event type (e.g. "assistant_message",
              "character_update", "character_intent").
        payload: Event-specific data. Schema depends on `type`.
    """

    protocol_version: str = PROTOCOL_VERSION
    event_id: str = ""
    session_id: str = ""
    turn_id: str = ""
    sequence: int = 0
    timestamp: float = 0.0
    source: str = "runtime"
    type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_id:
            self.event_id = f"evt_{uuid.uuid4().hex[:12]}"
        if not self.timestamp:
            self.timestamp = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "event_id": self.event_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "source": self.source,
            "type": self.type,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EventEnvelope":
        return cls(
            protocol_version=str(data.get("protocol_version", PROTOCOL_VERSION)),
            event_id=str(data.get("event_id", "")),
            session_id=str(data.get("session_id", "")),
            turn_id=str(data.get("turn_id", "")),
            sequence=int(data.get("sequence", 0)),
            timestamp=float(data.get("timestamp", 0)),
            source=str(data.get("source", "")),
            type=str(data.get("type", "")),
            payload=dict(data.get("payload", {})),
        )


# ── Validation ───────────────────────────────────────────────────────────


class EnvelopeValidationError(ValueError):
    """Raised when an envelope fails validation."""


# Event types that do not require a turn_id (system-level events)
SYSTEM_EVENT_TYPES = frozenset({
    "session.opened", "runtime.status", "ping", "pong", "error",
})


def validate_version(version: str) -> None:
    """Raise EnvelopeValidationError if the protocol version is unsupported."""
    if version in SUPPORTED_VERSIONS:
        return
    if version in LEGACY_VERSIONS:
        raise EnvelopeValidationError(
            f"Unsupported protocol version: {version}. "
            f"Consider upgrading the client. Supported: {SUPPORTED_VERSIONS}"
        )
    raise EnvelopeValidationError(
        f"Unknown protocol version: {version}. "
        f"Supported: {SUPPORTED_VERSIONS | LEGACY_VERSIONS}"
    )


def validate_envelope(envelope: EventEnvelope) -> None:
    """Validate an envelope, raising EnvelopeValidationError on failure.

    Checks performed:
      - protocol_version is supported
      - event_id is non-empty
      - session_id is non-empty for turn events
      - turn_id is non-empty for turn events (system events exempt)
      - type is non-empty
      - sequence >= 0
    """
    if not envelope.protocol_version:
        raise EnvelopeValidationError("protocol_version is required")
    validate_version(envelope.protocol_version)
    if not envelope.event_id:
        raise EnvelopeValidationError("event_id is required")
    if not envelope.type:
        raise EnvelopeValidationError("type is required")
    if envelope.sequence < 0:
        raise EnvelopeValidationError("sequence must be >= 0")
    # System-level events do not require a turn_id or session_id.
    # Turn events must carry both so the runtime can route correctly.
    if envelope.type not in SYSTEM_EVENT_TYPES:
        if not envelope.session_id:
            raise EnvelopeValidationError("session_id is required for turn events")
        if not envelope.turn_id:
            raise EnvelopeValidationError("turn_id is required for turn events")


# ── Error response helper ───────────────────────────────────────────────


def error_envelope(
    code: str,
    message: str,
    *,
    event_id: str = "",
    session_id: str = "",
    turn_id: str = "",
    sequence: int = 0,
) -> EventEnvelope:
    """Create a structured error envelope (type="error")."""
    return EventEnvelope(
        event_id=event_id or f"evt_{uuid.uuid4().hex[:12]}",
        session_id=session_id,
        turn_id=turn_id,
        sequence=sequence,
        source="runtime",
        type="error",
        payload={"code": code, "message": message},
    )


# ── Sequence tracker (dedup / ordering) ─────────────────────────────────


class SequenceTracker:
    """Tracks incoming message sequences per sender for dedup and ordering.

    Usage:
        tracker = SequenceTracker()
        is_new = tracker.accept("runtime", 42)  # True if this is a new message
        is_new = tracker.accept("runtime", 42)  # False (duplicate)
    """

    def __init__(self):
        self._last_sequence: dict[str, int] = {}

    def accept(self, source: str, sequence: int) -> bool:
        """Accept a message from source with given sequence.

        Returns True if the message is new (not a duplicate).
        Returns False if the sequence has already been seen.
        """
        key = source
        last = self._last_sequence.get(key, -1)
        if sequence > last:
            self._last_sequence[key] = sequence
            return True
        return False

    def reset(self, source: str = "") -> None:
        if source:
            self._last_sequence.pop(source, None)
        else:
            self._last_sequence.clear()
