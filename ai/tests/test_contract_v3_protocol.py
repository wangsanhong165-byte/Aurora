"""Contract tests for the canonical V3 envelope boundary."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts.v3.envelope import (
    CANONICAL_ENVELOPE_FIELDS,
    PROTOCOL_VERSION,
    EnvelopeValidationError,
    EventEnvelope,
    SequenceTracker,
    error_envelope,
    validate_envelope,
    validate_version,
)


def envelope(**overrides) -> EventEnvelope:
    values = {
        "event_type": "user.text",
        "session_id": "session-1",
        "turn_id": "turn-1",
        "sequence": 1,
        "source": "frontend",
        "payload": {"text": "hello"},
    }
    values.update(overrides)
    return EventEnvelope(**values)


def test_envelope_generates_identity_and_timestamp() -> None:
    event = envelope()
    assert event.protocol_version == PROTOCOL_VERSION
    assert event.event_id.startswith("evt_")
    assert event.timestamp > 0


def test_envelope_serializes_only_canonical_camel_case_fields() -> None:
    raw = envelope().to_dict()
    assert tuple(raw) == CANONICAL_ENVELOPE_FIELDS
    assert "protocol_version" not in raw
    assert "type" not in raw


def test_envelope_round_trip_preserves_all_fields() -> None:
    original = envelope(event_id="evt-fixed", timestamp=123.0)
    assert EventEnvelope.from_dict(original.to_dict()) == original


@pytest.mark.parametrize("version", ["2.0", "0.0", "4.0"])
def test_non_v3_versions_are_rejected(version: str) -> None:
    with pytest.raises(EnvelopeValidationError, match="protocolVersion"):
        validate_version(version)


def test_validate_envelope_accepts_v3() -> None:
    validate_envelope(envelope())


def test_turn_event_requires_turn_id() -> None:
    with pytest.raises(ValidationError, match="turnId"):
        envelope(turn_id=None)


def test_system_event_allows_null_turn_id() -> None:
    event = envelope(
        event_type="runtime.status",
        turn_id=None,
        source="runtime",
        payload={"state": "idle"},
    )
    validate_envelope(event)


def test_sequence_must_start_at_one() -> None:
    with pytest.raises(ValidationError, match="sequence"):
        envelope(sequence=0)


def test_error_envelope_uses_protocol_error() -> None:
    event = error_envelope("invalid_payload", "bad payload", session_id="session-1")
    assert event.event_type == "protocol.error"
    assert event.payload["code"] == "invalid_payload"


def test_sequence_tracker_is_scoped_by_session() -> None:
    tracker = SequenceTracker()
    assert tracker.accept("session-1", 1)
    assert not tracker.accept("session-1", 1)
    assert tracker.accept("session-2", 1)


def test_sequence_tracker_rejects_out_of_order() -> None:
    tracker = SequenceTracker()
    assert tracker.accept("session-1", 2)
    assert not tracker.accept("session-1", 1)


def test_sequence_tracker_reset_is_session_scoped() -> None:
    tracker = SequenceTracker()
    tracker.accept("session-1", 1)
    tracker.reset("session-1")
    assert tracker.accept("session-1", 1)
