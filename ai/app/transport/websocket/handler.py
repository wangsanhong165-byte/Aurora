"""Typed V3 RuntimeEvent ingress for the CharacterTurn pipeline."""

from __future__ import annotations

import asyncio
import io
import logging
import struct
import wave
from typing import Awaitable, Callable

from app.avatar.controller import AvatarController
from app.avatar.protocol import AvatarRequest
from app.runtime.character_turn import CharacterTurn, TurnInput
from app.runtime.runtime import runtime as default_runtime
from app.transport.protocol import OutboundMessage
from app.transport.v3_emitter import V3Emitter
from contracts.v3.envelope import EventEnvelope, error_envelope
from contracts.v3.events import (
    CharacterControlRequestedPayload,
    CharacterSuggestionAcceptedPayload,
    CharacterSuggestionRejectedPayload,
    ManagementRequestedPayload,
    UserAudioChunkPayload,
    UserAudioCompletedPayload,
    UserAudioStartedPayload,
    UserTextPayload,
)

logger = logging.getLogger("transport.handler")

RuntimeResponse = EventEnvelope | OutboundMessage
PushEnvelope = Callable[[EventEnvelope], Awaitable[None]]


class RuntimeEventHandler:
    """Map typed V3 events to existing domain commands and CharacterTurn."""

    def __init__(
        self,
        runtime=None,
        send_message=None,
        avatar_controller: AvatarController | None = None,
    ):
        self.runtime = runtime or default_runtime
        self.send_message = send_message
        self.send_v3: PushEnvelope | None = None
        self.v3_emitter_factory = V3Emitter
        self.avatar = avatar_controller
        self._management = None
        self._audio_buffer: list[float] = []
        self._sample_rate = 16000
        self._audio_turn_id = ""
        self._audio_session_id = ""
        self._active_task: asyncio.Task[None] | None = None
        self._active_turn_id = ""

    @property
    def management(self):
        if self._management is None:
            from app.transport.management import ManagementHandler

            self._management = ManagementHandler()
        return self._management

    def enable_proactive_push(self) -> None:
        self.runtime.register_proactive_handler(self._on_proactive_reply)

    def disable_proactive_push(self) -> None:
        self.runtime.unregister_proactive_handler(self._on_proactive_reply)
        if self._active_task and not self._active_task.done():
            self._active_task.cancel()

    async def handle_event(self, event: EventEnvelope) -> list[RuntimeResponse]:
        event_type = event.event_type

        if event_type == "user.text":
            payload = self._payload(event, UserTextPayload)
            turn_input = TurnInput(
                text=payload.text,
                session_id=event.session_id,
                turn_id=event.turn_id or "",
            )
            return await self._start_or_run_turn(turn_input)

        if event_type == "user.audio.started":
            payload = self._payload(event, UserAudioStartedPayload)
            if self._active_turn_id and self._active_turn_id != event.turn_id:
                return [self._stale_turn(event)]
            self._audio_buffer.clear()
            self._sample_rate = payload.sample_rate
            self._audio_turn_id = event.turn_id or ""
            self._audio_session_id = event.session_id
            self._active_turn_id = self._audio_turn_id
            return []

        if event_type == "user.audio.chunk":
            payload = self._payload(event, UserAudioChunkPayload)
            if not self._matches_audio_turn(event):
                return [self._stale_turn(event)]
            self._audio_buffer.extend(payload.samples)
            return []

        if event_type == "user.audio.completed":
            payload = self._payload(event, UserAudioCompletedPayload)
            if not self._matches_audio_turn(event):
                return [self._stale_turn(event)]
            if payload.sample_rate:
                self._sample_rate = payload.sample_rate
            audio = self._audio_to_wav()
            self._clear_audio()
            if not audio:
                return [error_envelope(
                    "empty_audio",
                    "Audio turn completed without samples",
                    session_id=event.session_id,
                    turn_id=event.turn_id or "",
                )]
            return await self._start_or_run_turn(TurnInput(
                audio=audio,
                sample_rate=self._sample_rate,
                session_id=event.session_id,
                turn_id=event.turn_id or "",
            ))

        if event_type in {"user.audio.cancelled", "turn.cancelled"}:
            return await self._cancel_turn(event)

        if event_type == "management.requested":
            payload = self._payload(event, ManagementRequestedPayload)
            return await self.management.handle(
                payload.action,
                payload.params,
                payload.request_id,
            )

        if event_type == "character.control.requested":
            return await self._handle_avatar_request(
                event,
                self._payload(event, CharacterControlRequestedPayload),
            )

        if event_type == "character.suggestion.accepted":
            payload = self._payload(event, CharacterSuggestionAcceptedPayload)
            raw = await self.avatar.handle_accept(payload.suggestion_id) if self.avatar else []
            return self._avatar_responses(event, raw)

        if event_type == "character.suggestion.rejected":
            payload = self._payload(event, CharacterSuggestionRejectedPayload)
            raw = await self.avatar.handle_reject(payload.suggestion_id) if self.avatar else []
            return self._avatar_responses(event, raw)

        return [error_envelope(
            "unsupported_event",
            f"Unsupported runtime event: {event_type}",
            session_id=event.session_id,
            turn_id=event.turn_id or "",
        )]

    @staticmethod
    def _payload(event: EventEnvelope, expected_type):
        payload = event.payload
        if not isinstance(payload, expected_type):
            raise TypeError(
                f"{event.event_type} payload must be {expected_type.__name__}"
            )
        return payload

    async def _start_or_run_turn(self, turn_input: TurnInput) -> list[RuntimeResponse]:
        if self._active_turn_id and self._active_turn_id != turn_input.turn_id:
            return [error_envelope(
                "turn_in_progress",
                f"Turn {self._active_turn_id} is still active",
                session_id=turn_input.session_id,
                turn_id=turn_input.turn_id,
            )]
        self._active_turn_id = turn_input.turn_id

        if self.send_v3 is not None:
            self._active_task = asyncio.create_task(self._run_turn_and_push(turn_input))
            return []

        try:
            return await self._run_turn(turn_input)
        finally:
            self._active_turn_id = ""

    async def _run_turn_and_push(self, turn_input: TurnInput) -> None:
        try:
            await self._run_turn(turn_input)
        except asyncio.CancelledError:
            logger.info("Turn cancelled: %s", turn_input.turn_id)
            raise
        except Exception:
            logger.exception("V3 turn task failed: %s", turn_input.turn_id)
        finally:
            if self._active_turn_id == turn_input.turn_id:
                self._active_turn_id = ""
            self._active_task = None

    async def _run_turn(self, turn_input: TurnInput) -> list[RuntimeResponse]:
        emitter = self.v3_emitter_factory(
            session_id=turn_input.session_id,
            turn_id=turn_input.turn_id,
        )
        responses: list[RuntimeResponse] = []
        start_event = emitter.start()
        if self.send_v3 is not None:
            await self.send_v3(start_event)
        else:
            responses.append(start_event)

        async def confirm_tool(name, args, risk):
            if self.send_v3 is None:
                return False
            from app.runtime.tool_confirmation import tool_confirmation_broker

            async def notify(payload):
                await self.send_v3(EventEnvelope(
                    session_id=turn_input.session_id,
                    turn_id=turn_input.turn_id,
                    event_type="tool.requested",
                    sequence=1,
                    source="runtime",
                    payload={
                        "requestId": payload["request_id"],
                        "tool": payload["tool"],
                        "args": payload["args"],
                        "risk": payload["risk"],
                    },
                ))

            return await tool_confirmation_broker.request(notify, name, args, risk)

        turn: CharacterTurn = await self.runtime.handle_turn(
            turn_input,
            confirmation_callback=confirm_tool,
        )
        completion = emitter.emit_completion(turn)
        if self.send_v3 is not None:
            for event in completion:
                await self.send_v3(event)
        else:
            responses.extend(completion)
        return responses

    def _matches_audio_turn(self, event: EventEnvelope) -> bool:
        return bool(
            self._audio_turn_id
            and event.turn_id == self._audio_turn_id
            and event.session_id == self._audio_session_id
        )

    def _audio_to_wav(self) -> bytes:
        if not self._audio_buffer:
            return b""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self._sample_rate)
            samples = [
                max(-32768, min(32767, int(sample * 32767)))
                for sample in self._audio_buffer
            ]
            wav_file.writeframes(struct.pack(f"<{len(samples)}h", *samples))
        return buf.getvalue()

    def _clear_audio(self) -> None:
        self._audio_buffer.clear()
        self._audio_turn_id = ""
        self._audio_session_id = ""
        if self._active_task is None:
            self._active_turn_id = ""

    async def _cancel_turn(self, event: EventEnvelope) -> list[RuntimeResponse]:
        if self._active_turn_id and event.turn_id != self._active_turn_id:
            return [self._stale_turn(event)]
        self._clear_audio()
        if self._active_task and not self._active_task.done():
            self._active_task.cancel()
        self._active_turn_id = ""
        reason = getattr(event.payload, "reason", "cancelled")
        return [
            EventEnvelope(
                session_id=event.session_id,
                turn_id=event.turn_id,
                event_type="tts.cancelled",
                sequence=1,
                source="runtime",
                payload={"reason": reason},
            ),
            EventEnvelope(
                session_id=event.session_id,
                turn_id=event.turn_id,
                event_type="turn.cancelled",
                sequence=2,
                source="runtime",
                payload={"reason": reason},
            ),
        ]

    @staticmethod
    def _stale_turn(event: EventEnvelope) -> EventEnvelope:
        return error_envelope(
            "stale_turn",
            f"Event belongs to inactive turn {event.turn_id}",
            session_id=event.session_id,
            turn_id=event.turn_id or "",
        )

    async def _handle_avatar_request(
        self,
        event: EventEnvelope,
        payload: CharacterControlRequestedPayload,
    ) -> list[RuntimeResponse]:
        if not self.avatar:
            return []
        params = payload.params
        request = AvatarRequest(
            target=str(params.get("target", "")),
            name=str(params.get("name", "")),
            action=payload.action,
            source=str(params.get("source", "user")),
            priority=int(params.get("priority", 100)),
        )
        return self._avatar_responses(event, await self.avatar.handle_request(request))

    def _avatar_responses(
        self,
        request: EventEnvelope,
        messages: list[dict],
    ) -> list[RuntimeResponse]:
        mapping = {
            "avatar_component": "character.component",
            "avatar_expression": "character.expression",
            "avatar_motion": "character.motion",
            "avatar_state": "character.snapshot",
            "avatar_suggestion": "character.suggestion",
        }
        results: list[RuntimeResponse] = []
        for message in messages:
            old_type = str(message.get("type", ""))
            event_type = mapping.get(old_type)
            if not event_type:
                continue
            payload = {
                {
                    "display_name": "displayName",
                    "param_ids": "paramIds",
                    "expression_intensity": "expressionIntensity",
                    "suggestion_id": "suggestionId",
                }.get(key, key): value
                for key, value in message.items()
                if key not in {"type", "model_id"}
            }
            results.append(EventEnvelope(
                session_id=request.session_id,
                turn_id=request.turn_id,
                event_type=event_type,
                sequence=1,
                source="runtime",
                payload=payload,
            ))
        return results

    async def _on_proactive_reply(self, turn: CharacterTurn) -> None:
        if self.send_v3 is None:
            return
        emitter = self.v3_emitter_factory(
            session_id=turn.session_id,
            turn_id=turn.turn_id,
        )
        await self.send_v3(emitter.start())
        for event in emitter.emit_completion(turn):
            await self.send_v3(event)
