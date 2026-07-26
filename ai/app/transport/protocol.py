"""Runtime Protocol V2 — formal message types between Frontend and Runtime.

Every message that crosses the WebSocket boundary is defined here.
The Transport layer serializes/deserializes to/from these types.
No business logic lives in this layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Inbound: Frontend → Runtime ──


@dataclass
class TextInput:
    """Text input from the user."""
    type: str = "text_input"
    text: str = ""


@dataclass
class AudioInput:
    """Float32 PCM audio samples (chunked stream)."""
    type: str = "audio_input"
    samples: list[float] = field(default_factory=list)
    sample_rate: int = 16000


@dataclass
class AudioEnd:
    """Marks the end of an audio input stream."""
    type: str = "audio_end"


@dataclass
class Interrupt:
    """Interrupt the current pipeline execution."""
    type: str = "interrupt"


@dataclass
class Ping:
    """Keepalive probe."""
    type: str = "ping"


@dataclass
class Command:
    """Generic management/auxiliary command.

    Replaces all individual management message types (get_histories,
    switch_character, set_pinned, etc.) with a single action+params pattern.
    """
    type: str = "command"
    action: str = ""       # e.g. "get_histories", "switch_character", "set_pinned"
    params: dict[str, Any] = field(default_factory=dict)


# Avatar protocol types (inbound)
from app.avatar.protocol import AvatarRequestMsg, AvatarAcceptMsg, AvatarRejectMsg

InboundMessage = TextInput | AudioInput | AudioEnd | Interrupt | Ping | Command | AvatarRequestMsg | AvatarAcceptMsg | AvatarRejectMsg


# ── Outbound: Runtime → Frontend ──


@dataclass
class AssistantMessage:
    """Complete assistant reply text."""
    type: str = "assistant_message"
    text: str = ""
    reasoning: str = ""
    segments: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass
class UserMessage:
    """User message forwarded from ASR transcription (voice input)."""
    type: str = "user_message"
    text: str = ""


@dataclass
class AssistantChunk:
    """Streaming chunk of assistant reply."""
    type: str = "assistant_chunk"
    text: str = ""
    delta: str = ""


@dataclass
class TtsStart:
    """Signal that TTS audio generation has started."""
    type: str = "tts_start"
    format: str = "wav"
    sequence: int = 0


@dataclass
class TtsAudio:
    """TTS audio data (base64-encoded WAV)."""
    type: str = "tts_audio"
    data: str = ""  # base64-encoded audio bytes
    format: str = "wav"
    sequence: int = 0
    volumes: list[float] = field(default_factory=list)  # RMS per 20ms chunk for lip-sync


@dataclass
class TtsEnd:
    """Signal that TTS audio playback is complete or was interrupted."""
    type: str = "tts_end"
    reason: str = "complete"  # "complete" | "interrupted" | "error"


@dataclass
class RuntimeStatus:
    """Runtime pipeline state change notification."""
    type: str = "runtime_status"
    state: str = ""       # "processing" | "speaking" | "idle" | "error"
    message: str = ""


@dataclass
class ToolConfirmation:
    type: str = "tool_confirmation"
    request_id: str = ""
    tool: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    risk: str = "confirm"


@dataclass
class CharacterUpdate:
    """Renderer-independent semantic presentation update for V3 clients."""
    type: str = "character_update"
    emotion: str = "neutral"
    intensity: float = 0.5
    speaking: bool = False
    timestamp: float = 0.0
    behavior: str = ""
    attention: str = "user"
    energy: float = 0.5
    duration_ms: int | None = None
    natural_vad: dict[str, float] | None = None
    context_tags: list[str] = field(default_factory=list)


@dataclass
class SessionEvent:
    """Session-level event (connection init, config, etc.)."""
    type: str = "session"
    status: str = ""  # "init" | "connected" | "disconnected"
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class Error:
    """Error notification from Runtime."""
    type: str = "error"
    code: str = ""
    message: str = ""


@dataclass
class Pong:
    """Keepalive response."""
    type: str = "pong"


@dataclass
class CommandResponse:
    """Response to a management command.

    Echoes the action name and carries action-specific data.
    """
    type: str = "command_response"
    action: str = ""           # echoes the request action
    data: dict[str, Any] = field(default_factory=dict)


OutboundMessage = (
    AssistantMessage | AssistantChunk | TtsStart | TtsAudio | TtsEnd
    | RuntimeStatus | CharacterUpdate
    | SessionEvent | Error | Pong | CommandResponse | UserMessage
    | ToolConfirmation
)


# ── Serialization helpers ──


def serialize(msg: OutboundMessage) -> dict[str, Any]:
    """Convert an outbound message to a JSON-safe dict."""
    return {k: v for k, v in msg.__dict__.items() if not k.startswith("_")}


MESSAGE_TYPE_MAP: dict[str, type] = {
    "text_input": TextInput,
    "audio_input": AudioInput,
    "audio_end": AudioEnd,
    "interrupt": Interrupt,
    "ping": Ping,
    "command": Command,
    # Avatar protocol
    "avatar_request": AvatarRequestMsg,
    "avatar_accept": AvatarAcceptMsg,
    "avatar_reject": AvatarRejectMsg,
}


def parse_inbound(raw: dict[str, Any]) -> InboundMessage:
    """Parse a raw dict into an inbound message object.

    Raises ValueError if the message type is unknown.
    """
    msg_type = raw.get("type", "")
    cls = MESSAGE_TYPE_MAP.get(msg_type)
    if cls is None:
        raise ValueError(f"Unknown message type: {msg_type}")
    # Extract only the fields the dataclass expects
    valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
    filtered = {k: v for k, v in raw.items() if k in valid_fields}
    return cls(**filtered)
