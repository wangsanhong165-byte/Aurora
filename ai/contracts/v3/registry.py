"""Parsing boundary from untrusted JSON into typed V3 runtime events."""

from __future__ import annotations

from typing import cast

from pydantic import JsonValue

from contracts.v3.envelope import EventEnvelope
from contracts.v3.events import EVENT_PAYLOAD_MODELS, PayloadModel


class UnsupportedEventError(ValueError):
    pass


class EventRegistry:
    @staticmethod
    def parse(raw: dict[str, JsonValue]) -> EventEnvelope[PayloadModel]:
        envelope = EventEnvelope.from_dict(raw)
        payload_model = EVENT_PAYLOAD_MODELS.get(envelope.event_type)
        if payload_model is None:
            raise UnsupportedEventError(f"Unsupported eventType: {envelope.event_type}")
        payload = payload_model.model_validate(envelope.payload)
        return cast(
            EventEnvelope[PayloadModel],
            EventEnvelope[payload_model](
                protocol_version=envelope.protocol_version,
                event_id=envelope.event_id,
                event_type=envelope.event_type,
                session_id=envelope.session_id,
                turn_id=envelope.turn_id,
                sequence=envelope.sequence,
                source=envelope.source,
                timestamp=envelope.timestamp,
                payload=payload,
            ),
        )


EVENT_MODELS = EVENT_PAYLOAD_MODELS
