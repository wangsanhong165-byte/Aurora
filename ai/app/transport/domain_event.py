"""Typed V3 events produced by the domain before transport identity is assigned."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from contracts.v3.envelope import EventEnvelope, EventSource
from contracts.v3.events import (
    EVENT_PAYLOAD_MODELS,
    TURN_EVENT_TYPES,
    PayloadModel,
)


@dataclass(frozen=True)
class DomainEvent:
    """A validated runtime event without connection-owned envelope fields."""

    event_type: str
    payload: PayloadModel
    turn_id: str | None = None
    source: EventSource = "runtime"

    @classmethod
    def create(
        cls,
        event_type: str,
        payload: PayloadModel | dict[str, Any],
        *,
        turn_id: str | None = None,
        source: EventSource = "runtime",
    ) -> "DomainEvent":
        payload_model = EVENT_PAYLOAD_MODELS.get(event_type)
        if payload_model is None:
            raise ValueError(f"Unsupported V3 domain event: {event_type}")
        if event_type in TURN_EVENT_TYPES and not turn_id:
            raise ValueError(f"turn_id is required for {event_type}")
        typed_payload = (
            payload
            if isinstance(payload, payload_model)
            else payload_model.model_validate(payload)
        )
        return cls(
            event_type=event_type,
            payload=typed_payload,
            turn_id=turn_id,
            source=source,
        )

    def to_envelope(self, session_id: str, sequence: int) -> EventEnvelope:
        return EventEnvelope(
            event_type=self.event_type,
            session_id=session_id,
            turn_id=self.turn_id,
            sequence=sequence,
            source=self.source,
            payload=self.payload,
        )
