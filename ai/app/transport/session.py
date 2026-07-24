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

logger = logging.getLogger("transport.session")

MessageHandler = Callable[[InboundMessage], Awaitable[list[OutboundMessage] | None]]


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

    async def run(self) -> None:
        """Accept the connection and enter the message loop."""
        await self.ws.accept()
        self._running = True

        # Send init event
        config = {
            "protocol_version": "1.0",
            "capabilities": ["text", "audio", "character_update", "tts", "pet_mode"],
        }
        if self.init_config_provider:
            config.update(self.init_config_provider())
        await self._send(SessionEvent(
            status="init",
            config=config,
        ))

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
        """Receive and dispatch messages until disconnect."""
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

                # Parse inbound message
                try:
                    message = parse_inbound(data)
                except ValueError:
                    continue

                # Handle pings directly at transport level
                if message.type == "ping":
                    await self._send(Pong())
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
        """Serialize and send an outbound message."""
        try:
            payload = serialize(message)
            await self.ws.send_text(json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass
