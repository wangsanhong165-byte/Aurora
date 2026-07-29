"""V3-only WebSocket session, identity, ordering, and dispatch."""

from __future__ import annotations

import asyncio
from collections import deque
import json
import logging
from typing import Any, Awaitable, Callable

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.transport.protocol import OutboundMessage, serialize
from contracts.v3.envelope import EventEnvelope, error_envelope
from contracts.v3.events import SessionOpenPayload
from contracts.v3.registry import EventRegistry, UnsupportedEventError

logger = logging.getLogger("transport.session")

SessionResponse = EventEnvelope | OutboundMessage
MessageHandler = Callable[[EventEnvelope], Awaitable[list[SessionResponse] | None]]


class WebSocketSession:
    """Own one V3 connection and reject all flat or non-V3 frames."""

    EVENT_ID_CACHE_SIZE = 2048

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
        self.init_config_provider = init_config_provider
        self.session_id = ""
        self._running = False
        self._incoming_sequence = 0
        self._outgoing_sequence = 0
        self._seen_event_ids: set[str] = set()
        self._event_id_order: deque[str] = deque()
        self._send_lock = asyncio.Lock()

    async def run(self) -> None:
        await self.ws.accept()
        self._running = True
        ping_task = asyncio.create_task(self._ping_loop())
        try:
            await self._message_loop()
        finally:
            self._running = False
            ping_task.cancel()
            try:
                await ping_task
            except asyncio.CancelledError:
                pass

    async def _message_loop(self) -> None:
        try:
            while self._running:
                try:
                    raw = await asyncio.wait_for(self.ws.receive_text(), timeout=300)
                except asyncio.TimeoutError:
                    if self.session_id:
                        await self._send_envelope(self._session_probe("session.ping"))
                    continue

                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    await self._send_protocol_error("invalid_json", "Frame is not valid JSON")
                    continue

                if not isinstance(data, dict):
                    await self._send_protocol_error("invalid_envelope", "Envelope must be an object")
                    continue
                if "protocolVersion" not in data:
                    await self._send_protocol_error(
                        "v3_required",
                        "Production WebSocket accepts V3 EventEnvelope only",
                    )
                    continue

                envelope = await self._parse_and_guard(data)
                if envelope is None:
                    continue

                if envelope.event_type == "session.open":
                    await self._open_session(envelope)
                    continue
                if not self.session_id:
                    await self._send_protocol_error(
                        "session_not_open",
                        "session.open must be the first event",
                        request=envelope,
                    )
                    continue
                if envelope.event_type == "session.ping":
                    nonce = str(getattr(envelope.payload, "nonce", ""))
                    await self._send_envelope(self._session_probe("session.pong", nonce))
                    continue
                if envelope.event_type == "session.pong":
                    continue

                try:
                    responses = await self.handler(envelope)
                except Exception as exc:
                    logger.exception("V3 handler failed")
                    await self._send_protocol_error(
                        "handler_error",
                        str(exc),
                        request=envelope,
                    )
                    continue

                for response in responses or []:
                    await self._send_response(response, envelope)
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("Session failed")

    async def _parse_and_guard(self, data: dict) -> EventEnvelope | None:
        try:
            raw_envelope = EventEnvelope.from_dict(data)
        except ValidationError as exc:
            code = (
                "unsupported_protocol_version"
                if "protocolVersion" in str(exc)
                else "invalid_envelope"
            )
            await self._send_protocol_error(code, str(exc))
            return None
        except Exception as exc:
            await self._send_protocol_error("invalid_envelope", str(exc))
            return None

        if self.session_id and raw_envelope.session_id != self.session_id:
            await self._send_protocol_error(
                "session_mismatch",
                f"Expected sessionId {self.session_id}",
                request=raw_envelope,
            )
            return None
        if not self.session_id and raw_envelope.event_type != "session.open":
            await self._send_protocol_error(
                "session_not_open",
                "session.open must be the first event",
                request=raw_envelope,
            )
            return None

        expected = self._incoming_sequence + 1
        if raw_envelope.sequence < expected:
            await self._send_protocol_error(
                "out_of_order",
                f"Expected sequence {expected}, got {raw_envelope.sequence}",
                request=raw_envelope,
            )
            return None
        if raw_envelope.sequence > expected:
            await self._send_protocol_error(
                "sequence_gap",
                f"Expected sequence {expected}, got {raw_envelope.sequence}",
                request=raw_envelope,
            )
            return None
        self._incoming_sequence = raw_envelope.sequence

        if raw_envelope.event_id in self._seen_event_ids:
            logger.info("Duplicate V3 event ignored: %s", raw_envelope.event_id)
            return None
        self._remember_event_id(raw_envelope.event_id)

        try:
            return EventRegistry.parse(data)
        except UnsupportedEventError as exc:
            await self._send_protocol_error(
                "unsupported_event",
                str(exc),
                request=raw_envelope,
            )
        except ValidationError as exc:
            await self._send_protocol_error(
                "invalid_payload",
                str(exc),
                request=raw_envelope,
            )
        return None

    async def _open_session(self, envelope: EventEnvelope) -> None:
        if self.session_id:
            await self._send_protocol_error(
                "session_already_open",
                "session.open may only be sent once",
                request=envelope,
            )
            return
        if not isinstance(envelope.payload, SessionOpenPayload):
            await self._send_protocol_error(
                "invalid_payload",
                "session.open payload is invalid",
                request=envelope,
            )
            return
        self.session_id = envelope.session_id
        config = self.init_config_provider() if self.init_config_provider else {}
        await self._send_envelope(EventEnvelope(
            session_id=self.session_id,
            event_type="session.opened",
            sequence=1,
            source="bridge",
            payload={
                "capabilities": envelope.payload.capabilities,
                "config": config,
            },
        ))

    async def _ping_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.ping_interval)
            if self._running and self.session_id:
                try:
                    await self._send_envelope(self._session_probe("session.ping"))
                except Exception:
                    break

    def _session_probe(self, event_type: str, nonce: str = "") -> EventEnvelope:
        return EventEnvelope(
            session_id=self.session_id or "session-unbound",
            event_type=event_type,
            sequence=1,
            source="runtime",
            payload={"nonce": nonce},
        )

    async def send(self, message: OutboundMessage) -> None:
        """Temporary V3-2 outbound wrapper; removed by the V3-3 emitter."""
        await self._send_response(message, None)

    async def send_envelope(self, envelope: EventEnvelope) -> None:
        await self._send_envelope(envelope)

    async def _send_response(
        self,
        response: SessionResponse,
        request: EventEnvelope | None,
    ) -> None:
        if isinstance(response, EventEnvelope):
            await self._send_envelope(response)
            return
        payload = serialize(response)
        old_type = str(payload.pop("type", getattr(response, "type", "")))
        event_type = old_type
        if old_type == "command_response":
            event_type = "management.result"
            payload = {
                "requestId": payload.get("request_id", ""),
                "action": payload.get("action", ""),
                "data": payload.get("data", {}),
            }
        elif old_type == "error" and request and request.event_type == "management.requested":
            event_type = "management.failed"
            request_id = getattr(request.payload, "request_id", "")
            action = getattr(request.payload, "action", "")
            payload = {
                "requestId": request_id,
                "action": action,
                "code": payload.get("code", "management_failed"),
                "message": payload.get("message", ""),
            }
        await self._send_envelope(EventEnvelope(
            session_id=self.session_id or (request.session_id if request else "session-unbound"),
            turn_id=request.turn_id if request else None,
            event_type=event_type,
            sequence=1,
            source="runtime",
            payload=payload,
        ))

    async def _send_protocol_error(
        self,
        code: str,
        message: str,
        *,
        request: EventEnvelope | None = None,
    ) -> None:
        await self._send_envelope(error_envelope(
            code,
            message,
            session_id=self.session_id or (request.session_id if request else "session-unbound"),
            turn_id=request.turn_id if request and request.turn_id else "",
        ))

    async def _send_envelope(self, envelope: EventEnvelope) -> None:
        async with self._send_lock:
            if self.session_id:
                envelope.session_id = self.session_id
            envelope.sequence = self._next_sequence()
            await self._send_raw(envelope.to_dict())

    async def _send_raw(self, message: dict) -> None:
        await self.ws.send_text(json.dumps(message, ensure_ascii=False))

    def _next_sequence(self) -> int:
        self._outgoing_sequence += 1
        return self._outgoing_sequence

    def _remember_event_id(self, event_id: str) -> None:
        self._seen_event_ids.add(event_id)
        self._event_id_order.append(event_id)
        while len(self._event_id_order) > self.EVENT_ID_CACHE_SIZE:
            expired = self._event_id_order.popleft()
            self._seen_event_ids.discard(expired)
