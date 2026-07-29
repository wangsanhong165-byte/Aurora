"""Deprecated V2 inbound definitions retained only until final V3 cleanup."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.avatar.protocol import AvatarAcceptMsg, AvatarRejectMsg, AvatarRequestMsg


@dataclass
class TextInput:
    type: str = "text_input"
    text: str = ""


@dataclass
class AudioInput:
    type: str = "audio_input"
    samples: list[float] = field(default_factory=list)
    sample_rate: int = 16000


@dataclass
class AudioEnd:
    type: str = "audio_end"


@dataclass
class Interrupt:
    type: str = "interrupt"


@dataclass
class Ping:
    type: str = "ping"


@dataclass
class Command:
    type: str = "command"
    action: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    request_id: str = ""


InboundMessage = (
    TextInput
    | AudioInput
    | AudioEnd
    | Interrupt
    | Ping
    | Command
    | AvatarRequestMsg
    | AvatarAcceptMsg
    | AvatarRejectMsg
)

MESSAGE_TYPE_MAP: dict[str, type] = {
    "text_input": TextInput,
    "audio_input": AudioInput,
    "audio_end": AudioEnd,
    "interrupt": Interrupt,
    "ping": Ping,
    "command": Command,
    "avatar_request": AvatarRequestMsg,
    "avatar_accept": AvatarAcceptMsg,
    "avatar_reject": AvatarRejectMsg,
}


def parse_inbound(raw: dict[str, Any]) -> InboundMessage:
    msg_type = raw.get("type", "")
    cls = MESSAGE_TYPE_MAP.get(msg_type)
    if cls is None:
        raise ValueError(f"Unknown message type: {msg_type}")
    valid_fields = {item.name for item in cls.__dataclass_fields__.values()}
    return cls(**{key: value for key, value in raw.items() if key in valid_fields})
