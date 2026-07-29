"""V3 Event Emitter — generates V3 EventEnvelopes directly from CharacterTurn.

This replaces TransportEmitter in the V3 path. V2 compatibility is preserved
through the existing TransportEmitter for legacy clients.
"""

from __future__ import annotations

import base64
import logging
from typing import Callable

from contracts.v3.envelope import EventEnvelope
from app.runtime.character_turn import CharacterTurn
from app.telemetry import get_session_id

logger = logging.getLogger("transport.v3_emitter")

SEQUENCE = 0


def _next_sequence() -> int:
    global SEQUENCE
    SEQUENCE += 1
    return SEQUENCE


class V3Emitter:
    """Emit V3 EventEnvelope lifecycle for a completed turn."""

    def __init__(self, session_id: str, turn_id: str, source: str = "runtime"):
        self.session_id = session_id or get_session_id()
        self.turn_id = turn_id
        self.source = source

    def _event(self, event_type: str, payload: dict) -> EventEnvelope:
        return EventEnvelope(
            session_id=self.session_id,
            turn_id=self.turn_id,
            sequence=_next_sequence(),
            event_type=event_type,
            payload=payload,
            source=self.source,
        )

    def start(self) -> EventEnvelope:
        """Create V3 runtime.status event before any work begins."""
        return EventEnvelope(
            session_id=self.session_id,
            event_type="runtime.status",
            sequence=_next_sequence(),
            payload={"state": "processing", "message": "Thinking..."},
            source=self.source,
        )

    def emit_completion(self, turn: CharacterTurn) -> list[EventEnvelope]:
        """Build an ordered list of V3 EventEnvelopes for a completed turn."""
        if turn.error:
            return [
                self._event("turn.failed", {
                    "code": turn.error.code,
                    "message": turn.error.message,
                }),
                EventEnvelope(
                    session_id=self.session_id,
                    event_type="runtime.status",
                    sequence=_next_sequence(),
                    payload={"state": "idle", "message": ""},
                    source=self.source,
                ),
            ]

        envelopes: list[EventEnvelope] = []

        # Turn started
        envelopes.append(self._event("turn.started", {
            "origin": "user",
            "inputMode": "audio" if turn.input.audio else "text",
        }))

        # Assistant text
        envelopes.append(self._event("assistant.text.started", {}))
        envelopes.append(self._event("assistant.text.completed", {
            "text": turn.reply_text,
            "reasoning": turn.reasoning or "",
        }))

        # TTS audio
        if turn.audio:
            envelopes.append(self._event("tts.started", {
                "format": "wav",
                "audioSequence": 0,
            }))
            envelopes.append(self._event("tts.audio", {
                "data": base64.b64encode(turn.audio).decode("ascii"),
                "format": "wav",
                "audioSequence": 0,
                "volumes": [],
            }))
            envelopes.append(self._event("tts.completed", {
                "reason": "complete",
            }))

        # Character intent (emotion, behavior, etc.)
        plan = turn.output.performance
        envelopes.append(self._event("character.intent", {
            "emotion": plan.emotion,
            "behavior": plan.behavior,
            "attention": plan.attention,
            "energy": plan.energy,
            "durationMs": plan.duration_ms,
            "contextTags": list(plan.context_tags),
        }))

        # Turn completed
        envelopes.append(self._event("turn.completed", {"reason": "complete"}))

        return envelopes
