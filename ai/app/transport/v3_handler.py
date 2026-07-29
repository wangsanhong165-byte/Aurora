"""V3 Event Handler — processes EventEnvelope directly, no V2 conversion.

System events (ping, session.opened, runtime.status) are handled inline.
Turn events are dispatched to the existing RuntimeEventHandler, which is
wrapped via a RuntimeCommand adapter that will be upgraded separately.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable

from contracts.v3.envelope import (
    EventEnvelope,
    SYSTEM_EVENT_TYPES,
    error_envelope,
)
from app.transport.protocol import InboundMessage, OutboundMessage, Pong

logger = logging.getLogger("transport.v3_handler")

# Event types that map to runtime pipeline turn inputs
TURN_EVENT_TYPES = frozenset({
    "text_input",
    "audio_input",
    "audio_end",
    "interrupt",
    "command",
    "avatar_request",
    "avatar_accept",
    "avatar_reject",
})

MessageHandler = Callable[[InboundMessage], Awaitable[list[OutboundMessage] | None]]


class V3EventHandler:
    """Process V3 EventEnvelope without converting back to V2 message types.

    System events are handled directly. Turn events are built into
    InboundMessage and forwarded to the existing RuntimeEventHandler.
    The next phase will upgrade the turn path to emit V3 domain events.
    """

    def __init__(
        self,
        handler: MessageHandler,
        *,
        send_message: Callable[[OutboundMessage], Awaitable[None]] | None = None,
    ):
        self._handler = handler
        self._send_message = send_message

    async def handle(self, envelope: EventEnvelope) -> list[EventEnvelope]:
        """Route an envelope and return response envelopes."""
        if envelope.type in SYSTEM_EVENT_TYPES:
            return self._handle_system(envelope)

        if envelope.type in TURN_EVENT_TYPES:
            return await self._handle_turn(envelope)

        return [error_envelope(
            "unsupported_event",
            f"Unknown event type: {envelope.type}",
            session_id=envelope.session_id,
            turn_id=envelope.turn_id,
        )]

    def _handle_system(self, envelope: EventEnvelope) -> list[EventEnvelope]:
        """Handle system-level events that require no turn or pipeline."""
        if envelope.type == "ping":
            # Build a V3 pong response
            return [EventEnvelope(
                session_id=envelope.session_id,
                type="pong",
                source="runtime",
            )]
        if envelope.type == "pong":
            return []
        # Other system events are informational — no response needed
        return []

    async def _handle_turn(self, envelope: EventEnvelope) -> list[EventEnvelope]:
        """Convert a turn event to InboundMessage and dispatch to handler."""
        from app.transport.protocol import MESSAGE_TYPE_MAP

        msg_type = envelope.type
        payload = envelope.payload

        # Map V3 type back to V2 dataclass fields
        cls = MESSAGE_TYPE_MAP.get(msg_type)
        if cls is None:
            return [error_envelope(
                "unsupported_event",
                f"Unknown turn event type: {msg_type}",
                session_id=envelope.session_id,
                turn_id=envelope.turn_id,
            )]

        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in payload.items() if k in valid_fields}
        message: InboundMessage = cls(**filtered)

        try:
            responses = await self._handler(message)
            if not responses:
                return []
            # Wrap V2 outbound messages into V3 envelopes
            result: list[EventEnvelope] = []
            for resp in responses:
                result.append(self._v2_to_envelope(resp, envelope))
            return result
        except Exception as error:
            logger.error("V3 handler error: %s", error)
            return [error_envelope(
                "handler_error",
                str(error),
                session_id=envelope.session_id,
                turn_id=envelope.turn_id,
            )]

    def _v2_to_envelope(self, message: OutboundMessage, request: EventEnvelope) -> EventEnvelope:
        """Wrap a V2 OutboundMessage into a V3 EventEnvelope."""
        from app.transport.protocol import serialize

        payload = serialize(message)
        return EventEnvelope(
            protocol_version="3.0",
            session_id=request.session_id,
            turn_id=request.turn_id,
            type=getattr(message, "type", ""),
            payload=payload,
            source="runtime",
        )
