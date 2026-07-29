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
    InboundMessage,
    OutboundMessage,
    SessionEvent,
    Pong,
)
from contracts.v3.envelope import (
    EventEnvelope,
    validate_version,
    error_envelope,
    SYSTEM_EVENT_TYPES,
)
from app.telemetry import get_session_id

logger = logging.getLogger("transport.session")

MessageHandler = Callable[[InboundMessage], Awaitable[list[OutboundMessage] | None]]


class WebSocketSession:
    """Manages a single WebSocket connection lifecycle.

    Usage:
        session = WebSocketSession(websocket, handler)
        await session.run()

    Incoming V3 messages are routed through V3EventHandler.
    Legacy V2 messages are converted via V2CompatibilityAdapter,
    then also routed through V3EventHandler.
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
        self.session_id = get_session_id()

    async def run(self) -> None:
        """Accept the connection and enter the message loop."""
        await self.ws.accept()
        self._running = True

        # Send init event (V3 envelope)
        v3_session_id = self.session_id
        config = {
            "capabilities": ["text", "audio", "character_update", "tts", "pet_mode", "telemetry"],
        }
        if self.init_config_provider:
            config.update(self.init_config_provider())
        init_envelope = EventEnvelope(
            session_id=v3_session_id,
            event_type="session.opened",
            sequence=self._next_sequence(),
            payload={"capabilities": config.pop("capabilities"), "config": config},
            source="bridge",
        )
        await self._send_raw(init_envelope.to_dict())

        # Wire the V3 event handler and V2 compatibility adapter
        from app.transport.v3_handler import V3EventHandler
        from app.transport.v2_adapter import V2CompatibilityAdapter

        v3_handler = V3EventHandler(
            self.handler,
            send_message=self.send,
        )
        v2_adapter = V2CompatibilityAdapter(
            v3_handler.handle,
            default_session_id=v3_session_id,
        )

        ping_task = asyncio.create_task(self._ping_loop())
        try:
            await self._message_loop(v3_session_id, v3_handler, v2_adapter)
        finally:
            self._running = False
            ping_task.cancel()
            try:
                await ping_task
            except asyncio.CancelledError:
                pass

    async def _message_loop(
        self,
        session_id: str = "",
        v3_handler=None,
        v2_adapter=None,
    ) -> None:
        """Receive and dispatch messages until disconnect.

        V3 messages (protocol_version present) go directly to V3EventHandler.
        V2 flat messages go through V2CompatibilityAdapter → V3EventHandler.
        """
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

                # Handle outgoing messages sent by _ping_loop
                # (they're already dicts, no parse needed)
                if not isinstance(data, dict):
                    continue

                try:
                    if "protocolVersion" in data:
                        # V3 envelope path — direct to V3EventHandler
                        responses = await self._handle_v3(data, session_id, v3_handler)
                    else:
                        # V2 flat message path — via compatibility adapter
                        responses = v2_adapter.handle_raw(data)
                except Exception as exc:
                    logger.error("Message handling error: %s", exc)
                    responses = [error_envelope(
                        "handler_error",
                        str(exc),
                        session_id=session_id,
                    )]

                if responses:
                    for resp in responses:
                        if isinstance(resp, dict):
                            await self._send_raw(resp)
                        elif isinstance(resp, EventEnvelope):
                            await self._send_envelope(resp)
                        else:
                            # Legacy V2 OutboundMessage
                            await self._send(resp)

        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error("Session error: %s", e)

    async def _handle_v3(
        self,
        data: dict,
        session_id: str,
        v3_handler,
    ) -> list:
        """Parse, validate, and route a V3 envelope through V3EventHandler."""
        try:
            envelope = EventEnvelope.from_dict(data)
        except Exception as exc:
            return [error_envelope(
                "envelope_parse_error", str(exc),
                session_id=session_id,
            )]

        try:
            validate_version(envelope.protocol_version)
        except ValueError as exc:
            return [error_envelope(
                "unsupported_protocol_version",
                str(exc),
                session_id=envelope.session_id,
                turn_id=envelope.turn_id,
            )]

        # Handle pings directly at transport level
        if envelope.type == "session.ping":
            await self._send_envelope(EventEnvelope(
                session_id=session_id,
                event_type="session.pong",
                sequence=self._next_sequence(),
                source="runtime",
                payload={"nonce": str(envelope.payload.get("nonce", ""))},
            ))
            return []

        # Route through V3EventHandler
        return await v3_handler.handle(envelope)

    async def _ping_loop(self) -> None:
        """Send periodic pings to detect dead connections."""
        while self._running:
            await asyncio.sleep(self.ping_interval)
            if not self._running:
                break
            try:
                await self._send_envelope(EventEnvelope(
                    session_id=self.session_id,
                    event_type="session.ping",
                    sequence=self._next_sequence(),
                    source="runtime",
                    payload={"nonce": ""},
                ))
            except Exception:
                break

    async def send(self, message: OutboundMessage) -> None:
        """Public send — used by handler for proactive streaming messages."""
        await self._send(message)

    async def send_envelope(self, envelope: EventEnvelope) -> None:
        """Send a V3 EventEnvelope directly (no V2 wrapping)."""
        await self._send_envelope(envelope)

    async def _send(self, message: OutboundMessage) -> None:
        """Serialize and send an outbound message (V3 envelope)."""
        try:
            from app.transport.protocol import serialize

            payload = serialize(message)
            msg_type = getattr(message, "type", "")
            turn_id = (
                payload.get("diagnostics", {}).get("turn_id", "")
                if isinstance(payload.get("diagnostics"), dict)
                else ""
            )
            envelope = EventEnvelope(
                session_id=self.session_id,
                turn_id=turn_id,
                event_type=msg_type,
                sequence=self._next_sequence(),
                payload=payload,
                source="runtime",
            )
            await self._send_envelope(envelope)
        except Exception:
            pass

    async def _send_envelope(self, envelope: EventEnvelope) -> None:
        """Send a V3 EventEnvelope as JSON."""
        try:
            await self._send_raw(envelope.to_dict())
        except Exception:
            pass

    async def _send_raw(self, message: dict) -> None:
        """Send a raw dict as JSON."""
        try:
            await self.ws.send_text(json.dumps(message, ensure_ascii=False))
        except Exception:
            pass

    def _next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence
