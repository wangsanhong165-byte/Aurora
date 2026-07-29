"""V3 Event Emitter — generates V3 EventEnvelopes directly from CharacterTurn.

This replaces TransportEmitter in the V3 path. V2 compatibility is preserved
through the existing TransportEmitter for legacy clients.
"""

from __future__ import annotations

import base64
import time
import logging
from typing import Callable

from contracts.v3.envelope import EventEnvelope
from app.runtime.character_turn import CharacterTurn

logger = logging.getLogger("transport.v3_emitter")

SEQUENCE = 0


def _next_sequence() -> int:
    global SEQUENCE
    SEQUENCE += 1
    return SEQUENCE


class V3Emitter:
    """Emit V3 EventEnvelope lifecycle for a completed turn."""

    def __init__(self, session_id: str, turn_id: str, source: str = "runtime"):
        self.session_id = session_id
        self.turn_id = turn_id
        self.source = source

    def _event(self, event_type: str, payload: dict) -> EventEnvelope:
        return EventEnvelope(
            session_id=self.session_id,
            turn_id=self.turn_id,
            sequence=_next_sequence(),
            type=event_type,
            payload=payload,
            source=self.source,
        )

    def start(self) -> EventEnvelope:
        """Create V3 runtime.status event before any work begins."""
        return EventEnvelope(
            session_id=self.session_id,
            type="runtime.status",
            payload={"state": "processing", "message": "Thinking..."},
            source=self.source,
        )

    def emit_completion(self, turn: CharacterTurn) -> list[EventEnvelope]:
        """Build an ordered list of V3 EventEnvelopes for a completed turn."""
        if turn.error:
            return [
                self._event("turn.failed", {
                    "turnId": turn.turn_id,
                    "code": turn.error.code,
                    "message": turn.error.message,
                }),
                EventEnvelope(
                    session_id=self.session_id,
                    type="runtime.status",
                    payload={"state": "idle", "message": ""},
                    source=self.source,
                ),
            ]

        envelopes: list[EventEnvelope] = []

        # Turn started
        envelopes.append(self._event("turn.started", {"turnId": turn.turn_id}))

        # Assistant text
        envelopes.append(self._event("assistant.text", {
            "text": turn.reply_text,
            "reasoning": turn.reasoning or "",
        }))

        # TTS audio
        if turn.audio:
            envelopes.append(self._event("tts.started", {
                "format": "wav",
                "sequence": 0,
            }))
            envelopes.append(self._event("tts.audio", {
                "data": base64.b64encode(turn.audio).decode("ascii"),
                "format": "wav",
                "sequence": 0,
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
            "speaking": plan.speaking,
            "timestamp": time.time(),
            "durationMs": plan.duration_ms,
            "contextTags": list(plan.context_tags),
        }))

        # Turn completed
        envelopes.append(self._event("turn.completed", {"turnId": turn.turn_id}))

        return envelopes
