# Avatar Protocol — message types for AvatarController communication
# Extends the existing transport protocol with avatar-specific messages.
# These are serialized as JSON and sent over WebSocket.
#
# Inbound (Frontend → Server):
#   AvatarRequestMsg   — user control command
#   AvatarAcceptMsg    — user accepts AI suggestion
#   AvatarRejectMsg    — user rejects AI suggestion
#
# Outbound (Server → Frontend):
#   AvatarComponentUpdate  — component state changed
#   AvatarExpressionUpdate — expression changed
#   AvatarMotionUpdate     — motion changed
#   AvatarStateSnapshot    — full state on connect
#   AvatarSuggestionMsg    — AI suggestion for user approval

from dataclasses import dataclass, field
from typing import Any


# ── Outbound (Server → Frontend) ──

@dataclass
class AvatarComponentUpdate:
    """Sent when a component is enabled/disabled."""
    type: str = "avatar_component"
    name: str = ""                    # component config key: "goggles"
    display_name: str = ""            # display label: "护目镜"
    enabled: bool = False
    controller: str = "USER"
    priority: int = 100
    expression: str = ""              # .exp3.json file name for frontend
    param_ids: list[str] = field(default_factory=list)


@dataclass
class AvatarExpressionUpdate:
    """Sent when the character's expression changes."""
    type: str = "avatar_expression"
    name: str = ""                    # semantic emotion: "happy"
    intensity: float = 1.0
    controller: str = "AI"
    priority: int = 50


@dataclass
class AvatarMotionUpdate:
    """Sent when a motion/gesture is triggered."""
    type: str = "avatar_motion"
    name: str = ""                    # "wave"
    controller: str = "AI"
    priority: int = 50
    loop: bool = False


@dataclass
class AvatarStateSnapshot:
    """Full state snapshot sent on initial connection."""
    type: str = "avatar_state"
    components: dict[str, bool] = field(default_factory=dict)
    expression: str = "neutral"
    expression_intensity: float = 1.0
    motion: str = "idle"
    model_id: str = ""


@dataclass
class AvatarSuggestionMsg:
    """AI proposes a change; user must accept or reject."""
    type: str = "avatar_suggestion"
    target: str = ""                  # "component" | "expression" | "motion"
    name: str = ""                    # "glasses" | "happy" | "wave"
    action: str = ""                  # "enable" | "disable" | "toggle"
    reason: str = ""                  # "thinking_mode"
    suggestion_id: str = ""           # unique ID for accept/reject


# ── Inbound (Frontend → Server) ──

@dataclass
class AvatarRequestMsg:
    """User sends a control command to the server."""
    type: str = "avatar_request"
    target: str = ""                  # "component" | "expression" | "motion"
    name: str = ""                    # "glasses" | "happy" | "wave"
    action: str = ""                  # "enable" | "disable" | "toggle"
    source: str = "user"             # "user" | "ai"
    priority: int = 100


@dataclass
class AvatarAcceptMsg:
    """User accepts an AI suggestion."""
    type: str = "avatar_accept"
    suggestion_id: str = ""


@dataclass
class AvatarRejectMsg:
    """User rejects an AI suggestion."""
    type: str = "avatar_reject"
    suggestion_id: str = ""


# ── Internal data types (not serialized directly) ──

@dataclass
class AvatarRequest:
    """Internal representation of an avatar control request."""
    target: str       # "component" | "expression" | "motion"
    name: str         # "glasses" | "happy" | "wave"
    action: str       # "enable" | "disable" | "toggle"
    source: str       # "user" | "ai" | "system"
    priority: int     # PermissionLevel value
    reason: str = ""  # optional context for logging


@dataclass
class AvatarSuggestion:
    """Internal representation of an AI suggestion."""
    target: str       # "component" | "expression" | "motion"
    name: str
    action: str
    reason: str
    suggestion_id: str = ""


# ── Serialization helpers ──

def serialize_avatar_message(msg: Any) -> dict:
    """Convert an avatar protocol message to a JSON-serializable dict."""
    result = {}
    for field_name in msg.__dataclass_fields__:
        value = getattr(msg, field_name)
        result[field_name] = value
    return result


# Message type strings for registration in transport protocol
AVATAR_MESSAGE_TYPES: dict[str, type] = {
    "avatar_component": AvatarComponentUpdate,
    "avatar_expression": AvatarExpressionUpdate,
    "avatar_motion": AvatarMotionUpdate,
    "avatar_state": AvatarStateSnapshot,
    "avatar_suggestion": AvatarSuggestionMsg,
    "avatar_request": AvatarRequestMsg,
    "avatar_accept": AvatarAcceptMsg,
    "avatar_reject": AvatarRejectMsg,
}
