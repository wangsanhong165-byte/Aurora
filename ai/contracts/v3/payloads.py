"""V3 Protocol payload types — discriminated union of all event payload schemas.

Each payload type corresponds to an event `type` value.
"""
from __future__ import annotations

from typing import Any

# ── Inbound payload schemas (frontend → runtime) ─────────────────────────


def text_input_payload(text: str) -> dict:
    return {"text": text}


def audio_input_payload(samples: list[float], sample_rate: int) -> dict:
    return {"samples": samples, "sample_rate": sample_rate}


def audio_end_payload() -> dict:
    return {}


def interrupt_payload() -> dict:
    return {}


def ping_payload() -> dict:
    return {}


def command_payload(action: str, params: dict | None = None, request_id: str = "") -> dict:
    return {"action": action, "params": params or {}, "request_id": request_id}


# ── Outbound payload schemas (runtime → frontend) ────────────────────────


def assistant_message_payload(text: str, reasoning: str = "", segments: list | None = None, diagnostics: dict | None = None) -> dict:
    return {
        "text": text,
        "reasoning": reasoning,
        "segments": segments or [],
        "diagnostics": diagnostics or {},
    }


def assistant_chunk_payload(text: str, delta: str) -> dict:
    return {"text": text, "delta": delta}


def user_message_payload(text: str) -> dict:
    return {"text": text}


def runtime_status_payload(state: str, message: str = "") -> dict:
    return {"state": state, "message": message}


def tts_start_payload(format: str = "wav", sequence: int = 0) -> dict:
    return {"format": format, "sequence": sequence}


def tts_audio_payload(data: str, format: str = "wav", sequence: int = 0, volumes: list | None = None) -> dict:
    return {"data": data, "format": format, "sequence": sequence, "volumes": volumes or []}


def tts_end_payload(reason: str = "complete") -> dict:
    return {"reason": reason}


def character_update_payload(
    emotion: str = "neutral",
    intensity: float = 0.5,
    speaking: bool = False,
    timestamp: float = 0.0,
    behavior: str = "",
    attention: str = "user",
    energy: float = 0.5,
    duration_ms: int | None = None,
    natural_vad: dict | None = None,
    context_tags: list | None = None,
) -> dict:
    return {
        "emotion": emotion,
        "intensity": intensity,
        "speaking": speaking,
        "timestamp": timestamp,
        "behavior": behavior,
        "attention": attention,
        "energy": energy,
        "duration_ms": duration_ms,
        "natural_vad": natural_vad,
        "context_tags": context_tags or [],
    }


def tool_confirmation_payload(request_id: str, tool: str, args: dict, risk: str) -> dict:
    return {"request_id": request_id, "tool": tool, "args": args, "risk": risk}


def command_response_payload(action: str, data: dict, request_id: str = "") -> dict:
    return {"action": action, "data": data, "request_id": request_id}


def error_payload(code: str, message: str, request_id: str = "") -> dict:
    return {"code": code, "message": message, "request_id": request_id}


def session_event_payload(status: str, config: dict | None = None) -> dict:
    return {"status": status, "config": config or {}}


# ── Telemetry payload (carried in "telemetry" event type) ────────────────


def telemetry_payload(events: list[dict]) -> dict:
    return {"events": events}
