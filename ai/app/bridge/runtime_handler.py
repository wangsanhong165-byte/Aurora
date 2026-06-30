"""Runtime WebSocket handler — bridges WebSocket messages to Runtime.dispatch().

This replaces the monolithic _handle_text_input / _handle_voice_input in
bridge/server.py by routing all interaction through the v2 CompanionRuntime.

Usage:
    from app.bridge.runtime_handler import RuntimeWebSocketHandler
    handler = RuntimeWebSocketHandler()
    await handler.handle_text(websocket, "hello")
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

from app.runtime.event import Event, EventType
from app.runtime.runtime import runtime as default_runtime

logger = logging.getLogger("bridge.runtime")


class RuntimeWebSocketHandler:
    """Handles WebSocket messages by routing through CompanionRuntime.dispatch().

    Provides the same frontend-facing message format as the legacy bridge
    handlers but uses the v2 Pipeline internally.
    """

    def __init__(self, runtime=None):
        self.runtime = runtime or default_runtime

    async def _status_callback(self, websocket: WebSocket, msg: str) -> None:
        """Push a status update to the WebSocket client during pipeline execution."""
        await self._send(websocket, {"type": "status", "text": msg})

    async def handle_text(self, websocket: WebSocket, text: str) -> None:
        """Handle a text-input message via Runtime.dispatch()."""
        await self._send(websocket, {"type": "control", "text": "conversation-chain-start"})
        await self._send(websocket, {"type": "user-input-transcription", "text": text})

        event = Event(
            type=EventType.TEXT_RECEIVED,
            payload={"text": text},
            source="websocket",
        )
        ctx = await self.runtime.dispatch(
            event,
            status_callback=lambda msg: self._status_callback(websocket, msg),
        )

        if ctx.error:
            logger.warning("[Runtime] dispatch error: %s", ctx.error)
            await self._send(websocket, {"type": "error", "message": ctx.error})
            await self._send(websocket, {"type": "control", "text": "conversation-chain-end"})
            return

        reply = ctx.reply_text or ""
        if reply:
            await self._send(websocket, {"type": "full-text", "text": reply})

            # Send audio if available
            if ctx.audio:
                import base64
                b64 = base64.b64encode(ctx.audio).decode("ascii")
                await self._send(websocket, {
                    "type": "audio",
                    "audio": b64,
                    "display_text": {"text": reply, "name": "", "avatar": ""},
                    "actions": {"expressions": [ctx.emotion]},
                })

        logger.info("[Runtime] text handled: %.60s -> %.60s", text, reply)
        await self._send(websocket, {"type": "control", "text": "conversation-chain-end"})

    async def handle_voice(
        self,
        websocket: WebSocket,
        audio_bytes: bytes,
        sample_rate: int = 16000,
    ) -> None:
        """Handle a voice-input message via Runtime.dispatch()."""
        await self._send(websocket, {"type": "control", "text": "conversation-chain-start"})

        event = Event(
            type=EventType.SPEECH_RECEIVED,
            payload={"audio": audio_bytes, "sample_rate": sample_rate},
            source="websocket",
        )
        ctx = await self.runtime.dispatch(
            event,
            status_callback=lambda msg: self._status_callback(websocket, msg),
        )

        if ctx.error:
            logger.warning("[Runtime] voice dispatch error: %s", ctx.error)
            await self._send(websocket, {"type": "error", "message": ctx.error})
            await self._send(websocket, {"type": "control", "text": "conversation-chain-end"})
            return

        # Echo transcription
        if ctx.user_text:
            await self._send(websocket, {"type": "user-input-transcription", "text": ctx.user_text})

        reply = ctx.reply_text or ""
        if reply:
            await self._send(websocket, {"type": "full-text", "text": reply})

            if ctx.audio:
                import base64
                b64 = base64.b64encode(ctx.audio).encode("ascii")
                await self._send(websocket, {
                    "type": "audio",
                    "audio": b64,
                    "display_text": {"text": reply, "name": "", "avatar": ""},
                    "actions": {"expressions": [ctx.emotion]},
                })

        logger.info(
            "[Runtime] voice handled: %.60s -> %.60s",
            ctx.user_text or "(empty)", reply,
        )
        await self._send(websocket, {"type": "control", "text": "conversation-chain-end"})

    async def handle_proactive(self, websocket: WebSocket, idle_time: float = 5.0) -> None:
        """Handle a proactive (AI-speak-signal) message."""
        event = Event(
            type=EventType.INITIATIVE_TRIGGERED,
            payload={"idle_time": idle_time},
            source="scheduler",
        )
        ctx = await self.runtime.dispatch(
            event,
            status_callback=lambda msg: self._status_callback(websocket, msg),
        )

        if ctx.error or not ctx.reply_text:
            return

        await self._send(websocket, {"type": "control", "text": "conversation-chain-start"})
        await self._send(websocket, {"type": "full-text", "text": ctx.reply_text})
        if ctx.audio:
            import base64
            b64 = base64.b64encode(ctx.audio).decode("ascii")
            await self._send(websocket, {
                "type": "audio",
                "audio": b64,
                "display_text": {"text": ctx.reply_text, "name": "", "avatar": ""},
                "actions": {"expressions": [ctx.emotion]},
            })
        await self._send(websocket, {"type": "control", "text": "conversation-chain-end"})

    @staticmethod
    async def _send(websocket: WebSocket, msg: dict[str, Any]) -> None:
        """Send a JSON message to a WebSocket client."""
        try:
            await websocket.send_text(json.dumps(msg, ensure_ascii=False))
        except Exception:
            pass
