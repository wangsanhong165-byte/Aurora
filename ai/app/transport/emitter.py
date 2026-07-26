"""Canonical CharacterTurn to V2 transport message emission."""

from __future__ import annotations

import base64
import time

from app.runtime.character_turn import CharacterTurn
from app.transport.protocol import (
    AssistantMessage,
    CharacterUpdate,
    Error,
    OutboundMessage,
    RuntimeStatus,
    TtsAudio,
    TtsEnd,
    TtsStart,
)


class TransportEmitter:
    """Emit exactly one ordered V2 lifecycle for a completed turn."""

    def start(self) -> RuntimeStatus:
        """Create the status sent before Runtime begins any turn work."""
        return RuntimeStatus(state="processing", message="Thinking...")

    def emit_completion(self, turn: CharacterTurn) -> list[OutboundMessage]:
        """Emit only messages that are valid after Runtime has completed."""
        if turn.error:
            return [
                Error(code=turn.error.code, message=turn.error.message),
                RuntimeStatus(state="idle", message=""),
            ]

        messages: list[OutboundMessage] = [
            AssistantMessage(
                text=turn.reply_text,
                reasoning=turn.reasoning,
                segments=turn.segments,
                diagnostics={
                    "turn_id": turn.turn_id,
                    "metrics": turn.metrics,
                    "warnings": turn.warnings,
                    "llm_usage": turn.llm_usage,
                    "context_budget": turn.context_budget,
                    "tool_audit": turn.tool_audit,
                },
            ),
        ]
        if turn.audio:
            messages.extend([
                TtsStart(format="wav", sequence=0),
                TtsAudio(
                    data=base64.b64encode(turn.audio).decode("ascii"),
                    format="wav",
                    sequence=0,
                ),
                TtsEnd(reason="complete"),
            ])

        plan = turn.output.performance
        messages.append(CharacterUpdate(
            emotion=plan.emotion,
            intensity=plan.energy,
            behavior=plan.behavior,
            attention=plan.attention,
            energy=plan.energy,
            speaking=plan.speaking,
            timestamp=time.time(),
            duration_ms=plan.duration_ms,
            context_tags=list(plan.context_tags),
        ))
        messages.append(RuntimeStatus(state="idle", message=""))
        return messages

    def emit(self, turn: CharacterTurn) -> list[OutboundMessage]:
        """Build a complete buffered lifecycle for non-streaming callers."""
        completion = self.emit_completion(turn)
        if turn.error:
            return completion
        return [self.start(), *completion]
