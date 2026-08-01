"""Typed, single-owner data model for one character interaction turn."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.runtime.event import Event, EventType


class TurnOrigin(str, Enum):
    USER = "user"
    INITIATIVE = "initiative"
    TOOL = "tool"
    SYSTEM = "system"


class TurnPhase(str, Enum):
    CREATED = "created"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class TurnError:
    code: str
    message: str
    retryable: bool = False

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class TurnInput:
    text: str = ""
    audio: bytes = b""
    sample_rate: int = 16000
    session_id: str = ""
    turn_id: str = ""
    origin: TurnOrigin = TurnOrigin.USER
    screen_context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        payload_count = int(bool(self.text.strip())) + int(bool(self.audio))
        if payload_count != 1:
            raise ValueError("TurnInput requires exactly one primary payload")
        if self.audio and self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")

    def to_event(self) -> Event:
        if self.origin is TurnOrigin.INITIATIVE:
            event_type = EventType.INITIATIVE_TRIGGERED
            payload = {
                "display_text": self.text,
                "initiative": dict(self.metadata.get("initiative", {})),
            }
        elif self.audio:
            event_type = EventType.SPEECH_RECEIVED
            payload = {"audio": self.audio, "sample_rate": self.sample_rate}
        else:
            event_type = EventType.TEXT_RECEIVED
            payload = {"text": self.text}
        payload["screen_context"] = dict(self.screen_context)
        payload.update(self.metadata.get("event_payload", {}))
        return Event(type=event_type, payload=payload, source=self.origin.value)


@dataclass
class PerformancePlan:
    emotion: str = "neutral"
    behavior: str = ""
    intensity: float = 0.5
    attention: str = "user"
    energy: float = 0.5
    speaking: bool = False
    duration_ms: int | None = None
    context_tags: list[str] = field(default_factory=list)
    motion_plan: dict[str, Any] | None = None


@dataclass
class TurnOutput:
    reply_text: str = ""
    reasoning: str = ""
    segments: list[dict[str, Any]] = field(default_factory=list)
    performance: PerformancePlan = field(default_factory=PerformancePlan)
    audio: bytes = b""
    persistence: dict[str, Any] = field(default_factory=dict)


@dataclass
class CharacterTurn:
    input: TurnInput
    turn_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    phase: TurnPhase = TurnPhase.CREATED
    output: TurnOutput = field(default_factory=TurnOutput)
    error: TurnError | None = None
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    event: Event = field(init=False)
    session_id: str = ""
    telemetry: Any = None

    # Typed runtime-owned working fields. Pipeline steps may mutate these,
    # but durable character state is committed separately.
    character: Any = None
    character_self: Any = None
    conversation: Any = None
    memories: list[dict[str, Any]] = field(default_factory=list)
    initiative: dict[str, Any] = field(default_factory=dict)
    turn_count: int = 0
    context_budget: dict[str, Any] = field(default_factory=dict)
    llm_usage: dict[str, Any] = field(default_factory=dict)
    learned_memories: list[dict[str, Any]] = field(default_factory=list)
    tool_audit: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    tool_result_budgets: list[dict[str, Any]] = field(default_factory=list)
    status_message: str = ""
    status_callback: Any = None
    confirmation_callback: Any = None

    def __post_init__(self) -> None:
        self.event = self.input.to_event()
        if self.input.origin is TurnOrigin.INITIATIVE:
            self.initiative = dict(self.input.metadata.get("initiative", {}))

    @property
    def input_origin(self) -> str:
        return self.input.origin.value

    @property
    def user_text(self) -> str:
        return self.input.text

    @user_text.setter
    def user_text(self, value: str) -> None:
        object.__setattr__(self.input, "text", value)

    @property
    def reply_text(self) -> str:
        return self.output.reply_text

    @reply_text.setter
    def reply_text(self, value: str) -> None:
        self.output.reply_text = value

    @property
    def reasoning(self) -> str:
        return self.output.reasoning

    @reasoning.setter
    def reasoning(self, value: str) -> None:
        self.output.reasoning = value

    @property
    def segments(self) -> list[dict[str, Any]]:
        return self.output.segments

    @segments.setter
    def segments(self, value: list[dict[str, Any]]) -> None:
        self.output.segments = value

    @property
    def emotion(self) -> str:
        return self.output.performance.emotion

    @emotion.setter
    def emotion(self, value: str) -> None:
        self.output.performance.emotion = value

    @property
    def emotion_intensity(self) -> float:
        return self.output.performance.energy

    @emotion_intensity.setter
    def emotion_intensity(self, value: float) -> None:
        self.output.performance.energy = value

    @property
    def audio(self) -> bytes:
        return self.output.audio

    @audio.setter
    def audio(self, value: bytes) -> None:
        self.output.audio = value

    @property
    def live2d_intent(self) -> dict[str, Any]:
        plan = self.output.performance
        return {
            "emotion": plan.emotion,
            "behavior": plan.behavior,
            "attention": plan.attention,
            "energy": plan.energy,
            "speaking": plan.speaking,
            "duration_ms": plan.duration_ms,
            "context_tags": list(plan.context_tags),
            "motion_plan": plan.motion_plan,
        }

    @live2d_intent.setter
    def live2d_intent(self, value: dict[str, Any]) -> None:
        from app.runtime.character_intent import CharacterIntent

        plan = self.output.performance
        plan.emotion = str(value.get("emotion", plan.emotion))
        plan.behavior = str(value.get("behavior", plan.behavior))
        plan.attention = str(value.get("attention", plan.attention))
        plan.energy = float(value.get("energy", value.get("intensity", plan.energy)))
        plan.speaking = bool(value.get("speaking", plan.speaking))
        plan.duration_ms = value.get("duration_ms")
        plan.context_tags = list(value.get("context_tags", ()))[:8]
        plan.motion_plan = CharacterIntent._motion_plan(
            value.get("motion_plan", value.get("motionPlan"))
        )

    def transition_to(self, phase: TurnPhase) -> None:
        if self.phase in {TurnPhase.COMPLETED, TurnPhase.FAILED, TurnPhase.CANCELLED}:
            raise ValueError(f"cannot transition terminal turn from {self.phase.value}")
        allowed = {
            TurnPhase.CREATED: {TurnPhase.PROCESSING, TurnPhase.CANCELLED},
            TurnPhase.PROCESSING: {
                TurnPhase.COMPLETED,
                TurnPhase.FAILED,
                TurnPhase.CANCELLED,
            },
        }
        if phase not in allowed.get(self.phase, set()):
            raise ValueError(f"invalid turn transition {self.phase.value} -> {phase.value}")
        self.phase = phase

    def fail(self, code: str, message: str, retryable: bool = False) -> None:
        if self.phase is TurnPhase.CREATED:
            self.phase = TurnPhase.PROCESSING
        self.error = TurnError(code=code, message=message, retryable=retryable)
        self.phase = TurnPhase.FAILED
