"""WebSocket session management.

Handles connection lifecycle, keepalive, and message routing.
No business logic — purely transport concerns.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Awaitable

from fastapi import WebSocket, WebSocketDisconnect

from app.transport.protocol import (
    parse_inbound,
    serialize,
    InboundMessage,
    OutboundMessage,
    SessionEvent,
    Pong,
)
from contracts.v3.envelope import (
    EventEnvelope,
    validate_version,
    error_envelope,
)
from app.telemetry import get_session_id

logger = logging.getLogger("transport.session")

MessageHandler = Callable[[InboundMessage], Awaitable[list[OutboundMessage] | None]]


def _envelope_to_inbound(envelope: EventEnvelope) -> InboundMessage | None:
    """Convert a V3 EventEnvelope to an InboundMessage for the handler.

    Returns None if the event type is unknown (caller should send error).
    """
    from app.transport.protocol import MESSAGE_TYPE_MAP, TextInput, AudioInput, AudioEnd, Interrupt, Ping, Command

    msg_type = envelope.type
    payload = envelope.payload

    # Map V3 types back to V2 dataclass fields
    cls = MESSAGE_TYPE_MAP.get(msg_type)
    if cls is None:
        return None
    # Filter to expected fields
    valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
    filtered = {k: v for k, v in payload.items() if k in valid_fields}
    return cls(**filtered)


class WebSocketSession:
    """Manages a single WebSocket connection lifecycle.

    Usage:
        session = WebSocketSession(websocket, handler)
        await session.run()
    """

    def __init__(
        self,
        websocket: WebSocket,
        handler: MessageHandler,
        ping_interval: float = 30.0,
        init_config_provider: Callable[[], dict[str, Any]] | None = None,
    ):
        self.ws = websocket
        self.handler = handler
        self.ping_interval = ping_interval
        self._running = False
        self.init_config_provider = init_config_provider
        self._sequence = 0

    async def run(self) -> None:
        """Accept the connection and enter the message loop."""
        await self.ws.accept()
        self._running = True

        # Send init event (V3 envelope)
        v3_session_id = get_session_id()
        config = {
            "protocol_version": "3.0",
            "capabilities": ["text", "audio", "character_update", "tts", "pet_mode", "telemetry"],
        }
        if self.init_config_provider:
            config.update(self.init_config_provider())
        init_envelope = EventEnvelope(
            session_id=v3_session_id,
            type="session",
            payload={"status": "init", "config": config},
            source="bridge",
        )
        await self._send_raw(init_envelope.to_dict())

        ping_task = asyncio.create_task(self._ping_loop())
        try:
            await self._message_loop(v3_session_id)
        finally:
            self._running = False
            ping_task.cancel()
            try:
                await ping_task
            except asyncio.CancelledError:
                pass

    async def _message_loop(self, session_id: str = "") -> None:
        """Receive and dispatch messages until disconnect.

        Supports both V2 flat messages and V3 envelopes.
        V2 messages are auto-wrapped via the compat layer.
        """
        from contracts.v3.compat import v2_flat_to_v3_envelope

        try:
            while self._running:
                try:
                    raw = await asyncio.wait_for(
                        self.ws.receive_text(), timeout=300
                    )
                except asyncio.TimeoutError:
                    # Long idle — probe connection
                    try:
                        await self._send(Pong())
                    except Exception:
                        break
                    continue

                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                # Detect V2 vs V3
                if "protocol_version" in data:
                    # V3 envelope
                    try:
                        envelope = EventEnvelope.from_dict(data)
                        self._sequence += 1
                        envelope.sequence = self._sequence
                    except Exception as exc:
                        await self._send_raw(error_envelope(
                            "envelope_parse_error", str(exc),
                            session_id=session_id,
                        ))
                        continue
                    # Validate the protocol version
                    try:
                        validate_version(envelope.protocol_version)
                    except ValueError as exc:
                        await self._send_raw(
                            error_envelope(
                                "unsupported_protocol_version",
                                str(exc),
                                session_id=envelope.session_id,
                                turn_id=envelope.turn_id,
                            )
                        )
                        continue
                    # Route based on type
                    # Handle pings directly at transport level
                    if envelope.type == "ping":
                        await self._send(Pong())
                        continue
                    # For now, convert envelope back to flat message for the handler
                    # (handler will be upgraded separately)
                    message = _envelope_to_inbound(envelope)
                    if message is None:
                        await self._send_raw(error_envelope(
                            "unsupported_event", f"Unknown event type: {envelope.type}",
                            session_id=envelope.session_id, turn_id=envelope.turn_id,
                        ))
                        continue
                else:
                    # V2 flat message — wrap in envelope
                    envelope = v2_flat_to_v3_envelope(
                        data,
                        default_session_id=session_id,
                        source="frontend",
                    )
                    message_type = data.get("type", "")
                    # Convert to InboundMessage
                    if message_type == "ping":
                        await self._send(Pong())
                        continue
                    try:
                        message = parse_inbound(data)
                    except ValueError:
                        continue

                # Route to application handler
                try:
                    responses = await self.handler(message)
                    if responses:
                        for resp in responses:
                            await self._send(resp)
                except Exception as e:
                    logger.error("Handler error: %s", e)
                    from app.transport.protocol import Error
                    await self._send(Error(
                        code="handler_error",
                        message=str(e),
                    ))

        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error("Session error: %s", e)

    async def _ping_loop(self) -> None:
        """Send periodic pings to detect dead connections."""
        while self._running:
            await asyncio.sleep(self.ping_interval)
            if not self._running:
                break
            try:
                await self.ws.send_text(json.dumps({"type": "ping"}))
            except Exception:
                break

    async def send(self, message: OutboundMessage) -> None:
        """Public send — used by handler for proactive streaming messages."""
        await self._send(message)

    async def _send(self, message: OutboundMessage) -> None:
        """Serialize and send an outbound message (V3 envelope)."""
        try:
            payload = serialize(message)
            # Determine the type from the message
            msg_type = getattr(message, "type", "")
            envelope = EventEnvelope(
                session_id=get_session_id(),
                turn_id=payload.get("diagnostics", {}).get("turn_id", "") if isinstance(payload.get("diagnostics"), dict) else "",
                type=msg_type,
                payload=payload,
                source="runtime",
            )
            await self._send_raw(envelope.to_dict())
        except Exception:
            pass

    async def _send_raw(self, message: dict) -> None:
        """Send a raw dict as JSON (used by V3 envelope flow)."""
        try:
            await self.ws.send_text(json.dumps(message, ensure_ascii=False))
        except Exception:
            pass
