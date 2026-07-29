"""Transport-neutral commands and domain events for avatar control."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AvatarRequest:
    target: str
    name: str
    action: str
    source: str
    priority: int
    reason: str = ""


@dataclass
class AvatarSuggestion:
    target: str
    name: str
    action: str
    reason: str
    suggestion_id: str = ""


@dataclass(frozen=True)
class AvatarComponentChanged:
    name: str
    display_name: str = ""
    enabled: bool = False
    controller: str = "USER"
    priority: int = 100
    expression: str = ""
    param_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AvatarExpressionChanged:
    name: str
    intensity: float = 1.0
    controller: str = "AI"
    priority: int = 50


@dataclass(frozen=True)
class AvatarMotionChanged:
    name: str
    controller: str = "AI"
    priority: int = 50
    loop: bool = False


@dataclass(frozen=True)
class AvatarStateRestored:
    components: dict[str, bool] = field(default_factory=dict)
    expression: str = "neutral"
    expression_intensity: float = 1.0
    motion: str = "idle"


@dataclass(frozen=True)
class AvatarSuggestionCreated:
    target: str
    name: str
    action: str
    reason: str
    suggestion_id: str


AvatarEvent = (
    AvatarComponentChanged
    | AvatarExpressionChanged
    | AvatarMotionChanged
    | AvatarStateRestored
    | AvatarSuggestionCreated
)
