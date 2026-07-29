"""Runtime Event Handler — bridges Transport Protocol to CharacterRuntime.

This is the ONLY place where transport messages are translated to Runtime
events. It is intentionally thin — no business logic, just protocol mapping.
"""

from __future__ import annotations

import logging

from app.runtime.character_turn import TurnInput
from app.runtime.runtime import runtime as default_runtime
from app.transport.protocol import (
    InboundMessage,
    OutboundMessage,
    TextInput,
    AudioInput,
    AudioEnd,
    Interrupt,
    TtsEnd,
    RuntimeStatus,
    UserMessage,
)
from app.avatar.controller import AvatarController
from app.avatar.protocol import (
    AvatarRequest,
    AvatarRequestMsg,
    AvatarAcceptMsg,
    AvatarRejectMsg,
)

logger = logging.getLogger("transport.handler")


class RuntimeEventHandler:
    """Translates Transport Protocol messages to CharacterRuntime.handle_turn().

    One instance per WebSocket connection. Manages a ManagementHandler
    for auxiliary operations via the generic Command message.

    If a send_message callback is provided, the handler can send
    streaming chunks (assistant_chunk) proactively during pipeline
    execution instead of returning them in the response list.
    """

    def __init__(
        self,
        runtime=None,
        send_message=None,
        avatar_controller: AvatarController | None = None,
    ):
        self.runtime = runtime or default_runtime
        self._audio_buffer: list[float] = []
        self._sample_rate = 16000
        self._management = None
        self.send_message = send_message
        self.send_v3 = None  # set by bridge if V3 emission is desired
        self.v3_emitter_factory = None  # V3Emitter class, set by bridge
        self.avatar = avatar_controller
        # Wire avatar push callback so it can broadcast to frontend
        if self.avatar and send_message:
            self.avatar.set_push_callback(send_message)

    def enable_proactive_push(self) -> None:
        """Register for proactive LLM responses from the runtime.

        Must be called after send_message is set. Responses are pushed
        to the frontend when the runtime generates a proactive reply.
        """
        self.runtime.register_proactive_handler(self._on_proactive_reply)

    def disable_proactive_push(self) -> None:
        """Unregister from proactive responses (connection closing)."""
        self.runtime.unregister_proactive_handler(self._on_proactive_reply)

    @property
    def management(self):
        if self._management is None:
            from app.transport.management import ManagementHandler
            self._management = ManagementHandler()
        return self._management

    async def handle(self, message: InboundMessage) -> list[OutboundMessage] | None:
        """Route an inbound message to the Runtime and return responses."""
        msg_type = message.type

        # ── Core pipeline messages ──
        if msg_type == "text_input":
            return await self._handle_text(message)
        elif msg_type == "audio_input":
            self._buffer_audio(message)
            return None
        elif msg_type == "audio_end":
            return await self._handle_audio_end()
        elif msg_type == "interrupt":
            return await self._handle_interrupt()

        # ── Management commands ──
        elif msg_type == "command":
            responses = await self.management.handle_command(message)
            for response in responses:
                if hasattr(response, "request_id"):
                    response.request_id = message.request_id
            return responses

        # ── Avatar control messages ──
        elif msg_type == "avatar_request":
            return await self._handle_avatar_request(message)
        elif msg_type == "avatar_accept":
            return await self._handle_avatar_accept(message)
        elif msg_type == "avatar_reject":
            return await self._handle_avatar_reject(message)

        else:
            return None

    async def _handle_text(self, msg: TextInput) -> list[OutboundMessage]:
        """Route text input through the Runtime and canonical emitter."""
        push_v3 = self.send_v3
        push_v2 = self.send_message

        # Send start message before handle_turn so the frontend shows thinking state
        v3_session_id = ""
        v3_turn_id = ""
        if push_v3:
            v3 = self.v3_emitter_factory(session_id="", turn_id="")
            await push_v3(v3.start())
            v3_session_id = v3.session_id
            v3_turn_id = v3.turn_id
        elif push_v2:
            from app.transport.emitter import TransportEmitter
            await push_v2(TransportEmitter().start())

        async def confirm_tool(name, args, risk):
            if not push_v2:
                return False
            from app.runtime.tool_confirmation import tool_confirmation_broker
            from app.transport.protocol import ToolConfirmation
            return await tool_confirmation_broker.request(
                lambda payload: push_v2(ToolConfirmation(**payload)),
                name, args, risk,
            )

        turn = await self.runtime.handle_turn(
            TurnInput(text=msg.text),
            confirmation_callback=confirm_tool,
        )

        if push_v3:
            v3 = self.v3_emitter_factory(
                session_id=v3_session_id or getattr(turn, "session_id", ""),
                turn_id=v3_turn_id or turn.turn_id,
            )
            for envelope in v3.emit_completion(turn):
                await push_v3(envelope)
            return []

        # V2 fallback
        from app.transport.emitter import TransportEmitter
        emitter = TransportEmitter()
        if push_v2:
            for response in emitter.emit_completion(turn):
                await push_v2(response)
            return []
        return emitter.emit(turn)

    def _buffer_audio(self, msg: AudioInput) -> None:
        """Buffer audio samples until stream ends."""
        self._audio_buffer.extend(msg.samples)

    async def _handle_audio_end(self) -> list[OutboundMessage]:
        """Process buffered audio through ASR + Runtime pipeline."""
        if not self._audio_buffer:
            return [RuntimeStatus(state="idle", message="")]

        # Convert float32 samples to WAV bytes
        import struct
        import io
        import wave

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self._sample_rate)
            samples_int16 = [
                max(-32768, min(32767, int(s * 32767)))
                for s in self._audio_buffer
            ]
            wf.writeframes(struct.pack(f"<{len(samples_int16)}h", *samples_int16))

        wav_bytes = buf.getvalue()
        self._audio_buffer = []

        push_v3 = self.send_v3
        push_v2 = self.send_message

        # Send start message before handle_turn
        v3_session_id = ""
        v3_turn_id = ""
        if push_v3:
            v3 = self.v3_emitter_factory(session_id="", turn_id="")
            await push_v3(v3.start())
            v3_session_id = v3.session_id
            v3_turn_id = v3.turn_id
        elif push_v2:
            from app.transport.emitter import TransportEmitter
            await push_v2(TransportEmitter().start())

        async def confirm_tool(name, args, risk):
            if not push_v2:
                return False
            from app.runtime.tool_confirmation import tool_confirmation_broker
            from app.transport.protocol import ToolConfirmation
            return await tool_confirmation_broker.request(
                lambda payload: push_v2(ToolConfirmation(**payload)),
                name, args, risk,
            )

        turn = await self.runtime.handle_turn(
            TurnInput(audio=wav_bytes, sample_rate=self._sample_rate),
            confirmation_callback=confirm_tool,
        )

        if push_v3:
            v3 = self.v3_emitter_factory(
                session_id=v3_session_id or getattr(turn, "session_id", ""),
                turn_id=v3_turn_id or turn.turn_id,
            )
            if turn.user_text:
                from contracts.v3.envelope import EventEnvelope
                await push_v3(EventEnvelope(
                    session_id=v3.session_id,
                    turn_id=v3.turn_id,
                    event_type="user.text",
                    sequence=1,
                    payload={"text": turn.user_text},
                ))
            for envelope in v3.emit_completion(turn):
                await push_v3(envelope)
            return []

        # V2 fallback
        from app.transport.emitter import TransportEmitter
        emitter = TransportEmitter()
        if push_v2:
            if turn.user_text:
                await push_v2(UserMessage(text=turn.user_text))
            for response in emitter.emit_completion(turn):
                await push_v2(response)
            return []
        return emitter.emit(turn)

    async def _handle_interrupt(self) -> list[OutboundMessage]:
        """Handle interrupt — send TTS end signal and reset state."""
        return [
            TtsEnd(reason="interrupted"),
            RuntimeStatus(state="idle", message="Interrupted"),
        ]

    # ── Avatar Control Handlers ────────────────────────────────────────

    async def _handle_avatar_request(self, msg: AvatarRequestMsg) -> list[dict]:
        """Process a user avatar control request through the AvatarController."""
        if not self.avatar:
            logger.warning("Avatar request received but no AvatarController configured")
            return []

        request = AvatarRequest(
            target=msg.target,
            name=msg.name,
            action=msg.action,
            source=msg.source,
            priority=msg.priority,
        )
        return await self.avatar.handle_request(request)

    async def _handle_avatar_accept(self, msg: AvatarAcceptMsg) -> list[dict]:
        """User accepted an AI suggestion."""
        if not self.avatar:
            return []
        return await self.avatar.handle_accept(msg.suggestion_id)

    async def _handle_avatar_reject(self, msg: AvatarRejectMsg) -> list[dict]:
        """User rejected an AI suggestion."""
        if not self.avatar:
            return []
        return await self.avatar.handle_reject(msg.suggestion_id)

    async def _on_proactive_reply(self, turn) -> None:
        """Push a proactive LLM response to the frontend.

        Called by CharacterRuntime when an initiative-triggered pipeline
        completes. Sends the same message types as _handle_text so the
        frontend displays the AI's message, plays audio, and updates the
        character — all without any user input.
        """
        if self.send_v3:
            v3 = self.v3_emitter_factory(
                session_id=getattr(turn, "session_id", ""),
                turn_id=turn.turn_id,
            )
            await self.send_v3(v3.start())
            for envelope in v3.emit_completion(turn):
                await self.send_v3(envelope)
            return
        if not self.send_message:
            return
        from app.transport.emitter import TransportEmitter
        for message in TransportEmitter().emit(turn):
            await self.send_message(message)
