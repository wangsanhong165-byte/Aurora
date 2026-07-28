"""Contract tests for V3 protocol envelope and compatibility layer.

These tests verify the protocol contract between frontend and backend.
They do NOT require any running services — they test the data types directly.
"""

from __future__ import annotations

import time

from contracts.v3.envelope import (
    EventEnvelope,
    PROTOCOL_VERSION,
    SUPPORTED_VERSIONS,
    LEGACY_VERSIONS,
    validate_version,
    validate_envelope,
    error_envelope,
    SequenceTracker,
    EnvelopeValidationError,
)
from contracts.v3.compat import (
    v2_flat_to_v3_envelope,
    v3_envelope_to_v2_flat,
    V2_TO_V3_TYPE,
)


# ── Envelope creation ───────────────────────────────────────────────────


def test_envelope_has_protocol_version():
    """Every envelope must carry a protocol version string."""
    env = EventEnvelope(type="test", payload={"hello": "world"})
    assert env.protocol_version == PROTOCOL_VERSION
    assert env.event_id.startswith("evt_")
    assert env.timestamp > 0


def test_envelope_auto_generates_event_id():
    """event_id must be auto-generated if not provided."""
    env = EventEnvelope(type="runtime_status")
    assert env.event_id
    assert env.event_id.startswith("evt_")


def test_envelope_to_dict_roundtrip():
    """Serialization to dict and back must preserve all fields."""
    original = EventEnvelope(
        protocol_version="3.0",
        session_id="ses_test123",
        turn_id="turn_test456",
        sequence=1,
        type="character_update",
        payload={"emotion": "happy", "intensity": 0.8},
    )
    data = original.to_dict()
    restored = EventEnvelope.from_dict(data)
    assert restored.protocol_version == original.protocol_version
    assert restored.session_id == original.session_id
    assert restored.turn_id == original.turn_id
    assert restored.sequence == original.sequence
    assert restored.type == original.type
    assert restored.payload == original.payload


# ── Version validation ─────────────────────────────────────────────────


def test_supported_version_passes():
    """Supported versions must validate without error."""
    validate_version("3.0")


def test_legacy_version_raises():
    """Legacy versions must raise EnvelopeValidationError with upgrade hint."""
    for version in LEGACY_VERSIONS:
        try:
            validate_version(version)
            assert False, f"Should have raised for {version}"
        except EnvelopeValidationError as e:
            assert "upgrade" in str(e).lower() or "unsupported" in str(e).lower()


def test_unknown_version_raises():
    """Unknown protocol versions must raise EnvelopeValidationError."""
    try:
        validate_version("0.0")
        assert False, "Should have raised for unknown version"
    except EnvelopeValidationError as e:
        assert "Unknown" in str(e)


# ── Envelope validation ────────────────────────────────────────────────


def test_valid_envelope_passes():
    """A complete, valid envelope must pass validation."""
    env = EventEnvelope(
        session_id="ses_test",
        turn_id="turn_test",
        sequence=1,
        type="runtime_status",
        payload={"state": "idle"},
    )
    # Should not raise
    validate_envelope(env)


def test_validate_requires_session_id():
    """Validation must reject envelopes without session_id."""
    env = EventEnvelope(session_id="", turn_id="turn_test", type="test")
    try:
        validate_envelope(env)
        assert False, "Should have raised"
    except EnvelopeValidationError as e:
        assert "session_id" in str(e)


def test_validate_requires_turn_id():
    """Validation must reject envelopes without turn_id."""
    env = EventEnvelope(session_id="ses_test", turn_id="", type="test")
    try:
        validate_envelope(env)
        assert False, "Should have raised"
    except EnvelopeValidationError as e:
        assert "turn_id" in str(e)


def test_validate_requires_type():
    """Validation must reject envelopes without type."""
    env = EventEnvelope(session_id="ses_test", turn_id="turn_test", type="")
    try:
        validate_envelope(env)
        assert False, "Should have raised"
    except EnvelopeValidationError as e:
        assert "type" in str(e)


def test_validate_rejects_negative_sequence():
    """Validation must reject sequences < 0."""
    env = EventEnvelope(session_id="ses_test", turn_id="turn_test", type="test", sequence=-1)
    try:
        validate_envelope(env)
        assert False
    except EnvelopeValidationError as e:
        assert "sequence" in str(e)


# ── Error envelope ─────────────────────────────────────────────────────


def test_error_envelope_has_error_type():
    """Error envelope must have type='error'."""
    env = error_envelope("test_error", "Something went wrong")
    assert env.type == "error"
    assert env.payload["code"] == "test_error"
    assert env.payload["message"] == "Something went wrong"


# ── Sequence tracker ───────────────────────────────────────────────────


def test_sequence_tracker_accepts_new():
    """SequenceTracker must accept a new, higher sequence."""
    tracker = SequenceTracker()
    assert tracker.accept("runtime", 1) is True
    assert tracker.accept("runtime", 2) is True


def test_sequence_tracker_rejects_duplicate():
    """SequenceTracker must reject a duplicate sequence."""
    tracker = SequenceTracker()
    tracker.accept("runtime", 1)
    assert tracker.accept("runtime", 1) is False


def test_sequence_tracker_rejects_out_of_order():
    """SequenceTracker must reject an out-of-order sequence."""
    tracker = SequenceTracker()
    tracker.accept("runtime", 2)
    assert tracker.accept("runtime", 1) is False


def test_sequence_tracker_reset():
    """SequenceTracker.reset must clear state for a source."""
    tracker = SequenceTracker()
    tracker.accept("runtime", 1)
    tracker.reset("runtime")
    assert tracker.accept("runtime", 1) is True


# ── V2→V3 conversion ──────────────────────────────────────────────────


def test_v2_flat_to_v3_envelope_basic():
    """V2 flat message must be wrapped in a V3 envelope with correct type."""
    v2 = {"type": "runtime_status", "state": "idle", "message": ""}
    env = v2_flat_to_v3_envelope(v2)
    assert env.protocol_version == "2.0"
    assert env.type == "runtime_status"
    assert env.payload["state"] == "idle"


def test_v2_field_remap_tone_to_emotion():
    """V2 'tone' field must be remapped to 'emotion' in V3 payload."""
    v2 = {"type": "character_update", "tone": "happy", "intensity": 0.7}
    env = v2_flat_to_v3_envelope(v2)
    assert "tone" not in env.payload
    assert env.payload["emotion"] == "happy"


def test_v2_field_remap_gesture_to_behavior():
    """V2 'gesture' field must be remapped to 'behavior' in V3 payload."""
    v2 = {"type": "character_update", "gesture": "wave"}
    env = v2_flat_to_v3_envelope(v2)
    assert "gesture" not in env.payload
    assert env.payload["behavior"] == "wave"


def test_v2_removed_fields_stripped():
    """V2 'intensity' field must be removed in V3 payload."""
    v2 = {"type": "character_update", "intensity": 0.9, "emotion": "happy"}
    env = v2_flat_to_v3_envelope(v2)
    assert "intensity" not in env.payload


def test_v2_to_v3_covers_all_types():
    """Every V2 message type must have a V3 mapping."""
    expected_types = {
        "text_input", "audio_input", "audio_end", "interrupt",
        "ping", "command",
        "assistant_message", "assistant_chunk", "user_message",
        "tts_start", "tts_audio", "tts_end",
        "runtime_status", "tool_confirmation",
        "character_update", "session", "error", "pong", "command_response",
        "avatar_request", "avatar_accept", "avatar_reject",
        "avatar_component", "avatar_expression", "avatar_motion",
        "avatar_state", "avatar_suggestion",
    }
    missing = expected_types - set(V2_TO_V3_TYPE.keys())
    assert not missing, f"V2 types missing from mapping: {missing}"


# ── V3→V2 conversion ──────────────────────────────────────────────────


def test_v3_to_v2_roundtrip():
    """V3 envelope converted to V2 flat must invert field remapping."""
    payload = {"emotion": "happy", "behavior": "speak"}
    env = EventEnvelope(
        session_id="ses_test",
        turn_id="turn_test",
        type="character_update",
        payload=payload,
    )
    v2 = v3_envelope_to_v2_flat(env)
    assert v2["type"] == "character_update"
    # "emotion" → "tone" (V2 field remap inversion)
    assert v2["tone"] == "happy"
    # "behavior" → "gesture" (V2 field remap inversion)
    assert v2["gesture"] == "speak"


# ── Discriminated union payload types ──────────────────────────────────


def test_payload_functions_produce_correct_payloads():
    """Payload factory functions must produce correct payload dicts."""
    from contracts.v3.payloads import (
        runtime_status_payload,
        character_update_payload,
        assistant_message_payload,
        error_payload,
    )

    p1 = runtime_status_payload(state="idle")
    assert p1["state"] == "idle"

    p2 = character_update_payload(emotion="happy")
    assert p2["emotion"] == "happy"
    assert p2["speaking"] is False

    p3 = assistant_message_payload(text="Hello", reasoning="thinking")
    assert p3["text"] == "Hello"
    assert p3["reasoning"] == "thinking"

    p4 = error_payload(code="test", message="error")
    assert p4["code"] == "test"
