"""Runtime Event Handler — bridges Transport Protocol to CompanionRuntime.

This is the ONLY place where transport messages are translated to Runtime
events. It is intentionally thin — no business logic, just protocol mapping.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any

from app.runtime.event import Event, EventType
from app.runtime.runtime import runtime as default_runtime
from app.transport.protocol import (
    InboundMessage,
    OutboundMessage,
    TextInput,
    AudioInput,
    AudioEnd,
    Interrupt,
    Command,
    AssistantMessage,
    AssistantChunk,
    TtsStart,
    TtsAudio,
    TtsEnd,
    CharacterAction,
    CharacterState,
    CharacterUpdate,
    RuntimeStatus,
    UserMessage,
    Error,
)
from app.avatar.controller import AvatarController
from app.avatar.permission import PermissionLevel
from app.avatar.protocol import (
    AvatarRequest,
    AvatarRequestMsg,
    AvatarAcceptMsg,
    AvatarRejectMsg,
    serialize_avatar_message,
)

logger = logging.getLogger("transport.handler")


def _compute_rms_volumes(wav_bytes: bytes, chunk_ms: int = 20) -> list[float]:
    """Extract RMS amplitude per chunk from WAV audio for lip-sync.

    Returns normalized volumes in [0, 1] range.
    Each entry corresponds to one chunk_ms of audio.
    """
    import io
    import struct
    import wave

    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            sample_rate = wf.getframerate()
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            frames = wf.readframes(wf.getnframes())

        chunk_samples = int(sample_rate * (chunk_ms / 1000))
        total_samples = len(frames) // sample_width
        fmt = {1: "b", 2: "<h"}.get(sample_width, "<h")
        samples = [struct.unpack(fmt, frames[i:i + sample_width])[0]
                   for i in range(0, len(frames), sample_width)]

        volumes: list[float] = []
        for start in range(0, len(samples), chunk_samples):
            chunk = samples[start:start + chunk_samples]
            if not chunk:
                break
            rms = (sum(s * s for s in chunk) / len(chunk)) ** 0.5
            # Normalize to 0-1 (typical 16-bit PCM max is 32767)
            norm = min(1.0, rms / 32767.0 * 3.0)  # 3x boost for quiet speech
            volumes.append(round(norm, 4))

        return volumes
    except Exception:
        return []


class RuntimeEventHandler:
    """Translates Transport Protocol messages to Runtime.dispatch() calls.

    One instance per WebSocket connection. Manages a ManagementHandler
    for auxiliary operations via the generic Command message.

    If a send_message callback is provided, the handler can send
    streaming chunks (assistant_chunk) proactively during pipeline
    execution instead of returning them in the response list.
    """

    def __init__(self, runtime=None, send_message=None, live2d_mapper=None, avatar_controller: AvatarController | None = None):
        self.runtime = runtime or default_runtime
        self._audio_buffer: list[float] = []
        self._sample_rate = 16000
        self._management = None
        self.send_message = send_message
        self.live2d_mapper = live2d_mapper
        self.avatar = avatar_controller
        # Compatibility handlers stay available for explicit avatar requests,
        # but runtime presentation is emitted only as character_update.
        self._legacy_avatar_push_enabled = False

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

    def _character_update(self, ctx) -> CharacterUpdate:
        intent = ctx.live2d_intent or {
            "emotion": ctx.emotion or "neutral",
            "intensity": ctx.emotion_intensity or 0.5,
            "gesture": ctx.segments[-1].get("gesture", "") if ctx.segments else "",
            "speaking": bool(ctx.audio),
        }

        # Route AI emotion/gesture through AvatarController permission system
        emotion = intent.get("emotion", "neutral")
        gesture = intent.get("behavior", intent.get("gesture", ""))

        if self.avatar and self._legacy_avatar_push_enabled:
            # AI expression requests are non-blocking — they may be denied if USER has taken control
            if emotion:
                asyncio.create_task(
                    self._ai_expression_request(emotion, float(intent.get("intensity", 0.5)))
                )
            if gesture:
                asyncio.create_task(
                    self._ai_motion_request(gesture)
                )

        mapped = self.live2d_mapper(intent) if self.live2d_mapper else {}

        # If AvatarController is active, use its current expression (which reflects
        # the permission system's result) rather than the raw intent
        if self.avatar and self._legacy_avatar_push_enabled:
            expr_state = self.avatar.expressions.get_current()
            motion_state = self.avatar.motions.get_current()
            expression = expr_state.preset or mapped.get("expression", emotion)
            motion = motion_state.name if motion_state.name != "idle" else ""
        else:
            expression = mapped.get("expression", emotion)
            motion = mapped.get("motion", gesture)

        return CharacterUpdate(
            model_id=mapped.get("model_id", ""),
            emotion=emotion,
            intensity=float(intent.get("intensity", 0.5)),
            expression=expression,
            motion=motion,
            speaking=bool(intent.get("speaking", False)),
            timestamp=time.time(),
            behavior=gesture,
            attention=intent.get("attention", "user"),
            energy=float(intent.get("energy", intent.get("intensity", 0.5))),
            duration_ms=intent.get("duration_ms") if isinstance(intent.get("duration_ms"), int) else None,
        )

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
            return await self.management.handle_command(message)

        # ── Avatar control messages ──
        elif msg_type == "avatar_request":
            return await self._handle_avatar_request(message)
        elif msg_type == "avatar_accept":
            return await self._handle_avatar_accept(message)
        elif msg_type == "avatar_reject":
            return await self._handle_avatar_reject(message)

        else:
            return None

    async def _send_chunks(self, text: str) -> None:
        """Send reply text as streaming chunks, then a final AssistantMessage."""
        if not self.send_message:
            return

        # Split into ~80-char overlapping chunks for smooth display
        chunk_size = 20
        pos = 0
        full = ""
        while pos < len(text):
            chunk = text[pos:pos + chunk_size]
            full += chunk
            msg = AssistantChunk(text=full, delta=chunk)
            await self.send_message(msg)
            pos += chunk_size
            await asyncio.sleep(0.02)  # small delay for natural streaming feel

    async def _handle_text(self, msg: TextInput) -> list[OutboundMessage]:
        """Route text input through the Runtime pipeline.

        When send_message is available, pushes messages proactively so the
        client sees progress immediately. Returns an empty list since the
        session's response-sending loop is superseded by proactive push.
        Falls back to returning the response list for legacy use.
        """
        responses: list[OutboundMessage] = []
        push = self.send_message

        # Push "Thinking..." immediately so the client isn't blocked
        # on LLM call + TTS synthesis time.
        status_proc = RuntimeStatus(state="processing", message="Thinking...")
        if push:
            await push(status_proc)
        responses.append(status_proc)

        event = Event(
            type=EventType.TEXT_RECEIVED,
            payload={"text": msg.text},
            source="websocket",
        )

        async def confirm_tool(name, args, risk):
            if not push:
                return False
            from app.runtime.tool_confirmation import tool_confirmation_broker
            from app.transport.protocol import ToolConfirmation
            return await tool_confirmation_broker.request(
                lambda payload: push(ToolConfirmation(**payload)),
                name, args, risk,
            )

        ctx = await self.runtime.dispatch(
            event, confirmation_callback=confirm_tool
        )

        if ctx.error:
            err = Error(code="runtime", message=ctx.error)
            idle = RuntimeStatus(state="idle", message="")
            if push:
                await push(err)
                await push(idle)
            responses.extend([err, idle])
            return responses if not push else []

        from app.modules.tts_preprocessor import clean_for_display
        reply = clean_for_display(ctx.reply_text or "")
        if reply:
            # Streaming chunks (only with proactive push)
            if push:
                await self._send_chunks(reply)

            # Full assistant message
            msg_assistant = AssistantMessage(text=reply, reasoning=ctx.reasoning, segments=ctx.segments or [])
            if push:
                await push(msg_assistant)
            responses.append(msg_assistant)

            if ctx.audio:
                start = TtsStart(format="wav", sequence=0)
                b64 = base64.b64encode(ctx.audio).decode("ascii")
                vols = _compute_rms_volumes(ctx.audio)
                audio_msg = TtsAudio(data=b64, format="wav", sequence=0, volumes=vols)
                end = TtsEnd(reason="complete")
                if push:
                    await push(start)
                    await push(audio_msg)
                    await push(end)
                responses.extend([start, audio_msg, end])

            update = self._character_update(ctx)
            if push:
                await push(update)
            responses.append(update)

        idle = RuntimeStatus(state="idle", message="")
        if push:
            await push(idle)
        responses.append(idle)

        # When proactive push is active, don't double-send via the response list
        return responses if not push else []

    def _buffer_audio(self, msg: AudioInput) -> None:
        """Buffer audio samples until stream ends."""
        self._audio_buffer.extend(msg.samples)

    async def _handle_audio_end(self) -> list[OutboundMessage]:
        """Process buffered audio through ASR + Runtime pipeline.

        Uses proactive push when send_message is available, so the client
        sees progress immediately. Sends a UserMessage with the ASR-transcribed
        text so the frontend can display what the user said.
        """
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
            # Convert float32 [-1,1] to int16
            samples_int16 = [
                max(-32768, min(32767, int(s * 32767)))
                for s in self._audio_buffer
            ]
            wf.writeframes(struct.pack(f"<{len(samples_int16)}h", *samples_int16))

        wav_bytes = buf.getvalue()
        self._audio_buffer = []

        responses: list[OutboundMessage] = []
        push = self.send_message

        # Push "Listening..." immediately so the client isn't blocked
        # on ASR + LLM + TTS pipeline time.
        status_listening = RuntimeStatus(state="processing", message="Listening...")
        if push:
            await push(status_listening)
        responses.append(status_listening)

        event = Event(
            type=EventType.SPEECH_RECEIVED,
            payload={"audio": wav_bytes, "sample_rate": self._sample_rate},
            source="websocket",
        )

        async def confirm_tool(name, args, risk):
            if not push:
                return False
            from app.runtime.tool_confirmation import tool_confirmation_broker
            from app.transport.protocol import ToolConfirmation
            return await tool_confirmation_broker.request(
                lambda payload: push(ToolConfirmation(**payload)),
                name, args, risk,
            )

        ctx = await self.runtime.dispatch(
            event, confirmation_callback=confirm_tool
        )

        if ctx.error:
            err = Error(code="runtime", message=ctx.error)
            idle = RuntimeStatus(state="idle", message="")
            if push:
                await push(err)
                await push(idle)
            responses.extend([err, idle])
            return responses if not push else []

        # Send UserMessage with ASR-transcribed text so the user can
        # see what they said in the chat UI.
        user_text = ctx.user_text or ""
        if user_text and push:
            await push(UserMessage(text=user_text))

        from app.modules.tts_preprocessor import clean_for_display
        reply = clean_for_display(ctx.reply_text or "")
        if reply:
            # Streaming chunks (only with proactive push)
            if push:
                await self._send_chunks(reply)

            # Full assistant message
            msg_assistant = AssistantMessage(text=reply, reasoning=ctx.reasoning, segments=ctx.segments or [])
            if push:
                await push(msg_assistant)
            responses.append(msg_assistant)

            if ctx.audio:
                start = TtsStart(format="wav", sequence=0)
                b64 = base64.b64encode(ctx.audio).decode("ascii")
                vols = _compute_rms_volumes(ctx.audio)
                audio_msg = TtsAudio(data=b64, format="wav", sequence=0, volumes=vols)
                end = TtsEnd(reason="complete")
                if push:
                    await push(start)
                    await push(audio_msg)
                    await push(end)
                responses.extend([start, audio_msg, end])

            update = self._character_update(ctx)
            if push:
                await push(update)
            responses.append(update)

        idle = RuntimeStatus(state="idle", message="")
        if push:
            await push(idle)
        responses.append(idle)

        # When proactive push is active, don't double-send via the response list
        return responses if not push else []

    async def _handle_interrupt(self) -> list[OutboundMessage]:
        """Handle interrupt — send TTS end signal and reset state."""
        return [
            TtsEnd(reason="interrupted"),
            CharacterState(
                activity="idle",
                emotion="neutral",
                intensity=0.5,
                expression="neutral",
                motion="",
            ),
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

    async def _ai_expression_request(self, emotion: str, intensity: float) -> None:
        """Non-blocking: submit AI expression decision to AvatarController."""
        request = AvatarRequest(
            target="expression",
            name=emotion,
            action="enable",
            source="ai",
            priority=PermissionLevel.AI,
            reason="llm_decision",
        )
        responses = await self.avatar.handle_request(request)
        # Push any resulting messages to frontend
        if self.send_message:
            for r in responses:
                await self.send_message(r)

    async def _ai_motion_request(self, gesture: str) -> None:
        """Non-blocking: submit AI gesture decision to AvatarController."""
        request = AvatarRequest(
            target="motion",
            name=gesture,
            action="enable",
            source="ai",
            priority=PermissionLevel.AI,
            reason="llm_decision",
        )
        responses = await self.avatar.handle_request(request)
        if self.send_message:
            for r in responses:
                await self.send_message(r)

    async def _on_proactive_reply(self, ctx) -> None:
        """Push a proactive LLM response to the frontend.

        Called by CompanionRuntime when an initiative-triggered pipeline
        completes. Sends the same message types as _handle_text so the
        frontend displays the AI's message, plays audio, and updates the
        character — all without any user input.
        """
        if not self.send_message:
            return
        from app.modules.tts_preprocessor import clean_for_display
        reply = clean_for_display(ctx.reply_text or "")
        if not reply:
            return

        push = self.send_message

        # 1. Status: processing so the UI shows activity
        await push(RuntimeStatus(state="processing", message="Thinking..."))

        # 2. Subtle user marker so the chat registers a new assistant slot
        await push(UserMessage(text="💭"))

        # 3. Streaming chunks for smooth display
        await self._send_chunks(reply)

        # 4. Final assistant message with segments
        await push(AssistantMessage(text=reply, reasoning=ctx.reasoning, segments=ctx.segments or []))

        # 5. TTS audio if available
        if ctx.audio:
            await push(TtsStart(format="wav", sequence=0))
            b64 = base64.b64encode(ctx.audio).decode("ascii")
            vols = _compute_rms_volumes(ctx.audio)
            await push(TtsAudio(data=b64, format="wav", sequence=0, volumes=vols))
            await push(TtsEnd(reason="complete"))

        # 6. Character state (emotion, expression, motion)
        update = self._character_update(ctx)
        await push(update)

        # 7. Back to idle
        await push(RuntimeStatus(state="idle", message=""))
