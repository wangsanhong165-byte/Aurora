"""V2 ↔ V3 protocol conversion.

This is the ONLY place where old protocol fields are handled.
No business code should read V2-style message formats directly.
"""

from __future__ import annotations

from contracts.v3.envelope import EventEnvelope

# ── V2 message type mapping (old string type → V3 event type) ────────────

V2_TO_V3_TYPE: dict[str, str] = {
    # Inbound (frontend → runtime)
    "text_input": "text_input",
    "audio_input": "audio_input",
    "audio_end": "audio_end",
    "interrupt": "interrupt",
    "ping": "ping",
    "command": "command",
    "avatar_request": "avatar_request",
    "avatar_accept": "avatar_accept",
    "avatar_reject": "avatar_reject",
    # Outbound (runtime → frontend)
    "assistant_message": "assistant_message",
    "assistant_chunk": "assistant_chunk",
    "user_message": "user_message",
    "tts_start": "tts_start",
    "tts_audio": "tts_audio",
    "tts_end": "tts_end",
    "runtime_status": "runtime_status",
    "tool_confirmation": "tool_confirmation",
    "character_update": "character_update",
    "session": "session",
    "error": "error",
    "pong": "pong",
    "command_response": "command_response",
    # Avatar protocol
    "avatar_component": "avatar_component",
    "avatar_expression": "avatar_expression",
    "avatar_motion": "avatar_motion",
    "avatar_state": "avatar_state",
    "avatar_suggestion": "avatar_suggestion",
}

# ── Legacy field remapping (V2 fields → V3 payload fields) ───────────────

# Fields that must be renamed when converting V2 → V3 payloads
V2_FIELD_REMAP: dict[str, str] = {
    "tone": "emotion",
    "gesture": "behavior",
    "request_id": "request_id",
    "model_id": "model",
    "conf_name": "config_name",
    "conf_uid": "config_uid",
    "client_uid": "client_uid",
}

# Fields that were removed in V3 (no longer valid)
V2_REMOVED_FIELDS = {
    "intensity",  # → use "energy" in V3
    "model_ready",
}


# ── Conversion functions ────────────────────────────────────────────────


def v2_flat_to_v3_envelope(raw: dict, *, default_session_id: str = "", default_turn_id: str = "", source: str = "bridge") -> EventEnvelope:
    """Convert a V2 flat message dict to a V3 EventEnvelope.

    V2 messages look like: {"type": "runtime_status", "state": "processing", ...}
    V3 envelopes look like: {"protocol_version": "3.0", ..., "type": "runtime_status", "payload": {"state": "processing", ...}}
    """
    msg_type = raw.get("type", "")
    v3_type = V2_TO_V3_TYPE.get(msg_type, msg_type)

    # Copy all fields except type into the payload
    payload = {k: v for k, v in raw.items() if k != "type"}

    # Apply field remapping
    for old_field, new_field in V2_FIELD_REMAP.items():
        if old_field in payload:
            payload[new_field] = payload.pop(old_field)

    # Remove deprecated fields
    for field in V2_REMOVED_FIELDS:
        payload.pop(field, None)

    return EventEnvelope(
        session_id=default_session_id or "session-legacy",
        turn_id=default_turn_id,
        event_type=v3_type,
        sequence=1,
        payload=payload,
    )


def v3_envelope_to_v2_flat(envelope: EventEnvelope) -> dict:
    """Convert a V3 EventEnvelope back to a V2 flat message dict.

    Used for backward compatibility with V2-only consumers (e.g., old frontend).
    """
    result = {"type": envelope.type}
    for key, value in envelope.payload.items():
        # Invert field remap
        v2_key = key
        for old_f, new_f in V2_FIELD_REMAP.items():
            if new_f == key:
                v2_key = old_f
                break
        result[v2_key] = value
    return result
