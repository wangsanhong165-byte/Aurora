"""CharacterTurn to typed V3 domain-event emission."""

from __future__ import annotations

import base64

from app.runtime.character_turn import CharacterTurn, TurnInput
from app.transport.domain_event import DomainEvent


class TransportEmitter:
    """Emit one ordered V3 lifecycle without WebSocket or session concerns."""

    @staticmethod
    def _event(
        turn: CharacterTurn,
        event_type: str,
        payload: dict,
    ) -> DomainEvent:
        return DomainEvent.create(
            event_type,
            payload,
            turn_id=turn.turn_id,
        )

    def start_input(self, turn_input: TurnInput) -> list[DomainEvent]:
        events = [
            DomainEvent.create("turn.started", {
                "origin": turn_input.origin.value,
                "inputMode": "audio" if turn_input.audio else (
                    "initiative" if turn_input.origin.value == "initiative" else "text"
                ),
            }, turn_id=turn_input.turn_id),
        ]
        if turn_input.audio:
            events.append(DomainEvent.create(
                "asr.started",
                {"language": None},
                turn_id=turn_input.turn_id,
            ))
        return events

    def start(self, turn: CharacterTurn) -> list[DomainEvent]:
        events = [
            self._event(turn, "turn.started", {
                "origin": turn.input_origin,
                "inputMode": "audio" if turn.input.audio else (
                    "initiative" if turn.input_origin == "initiative" else "text"
                ),
            }),
        ]
        if turn.input.audio:
            events.append(self._event(turn, "asr.started", {"language": None}))
        return events

    def emit_completion(self, turn: CharacterTurn) -> list[DomainEvent]:
        if turn.error:
            return [
                self._event(turn, "turn.failed", {
                    "code": turn.error.code,
                    "message": turn.error.message,
                }),
                DomainEvent.create(
                    "runtime.status",
                    {"state": "idle", "message": ""},
                ),
            ]

        events: list[DomainEvent] = []
        if turn.input.audio:
            events.append(self._event(turn, "asr.result", {
                "text": turn.user_text,
                "confidence": None,
                "language": None,
            }))

        for index, audit in enumerate(turn.tool_audit):
            tool = str(audit.get("tool", "unknown"))
            request_id = f"{turn.turn_id}:tool:{index}"
            events.append(self._event(turn, "tool.started", {
                "requestId": request_id,
                "tool": tool,
            }))
            if audit.get("status") == "ok":
                events.append(self._event(turn, "tool.result", {
                    "requestId": request_id,
                    "tool": tool,
                    "result": dict(audit),
                }))
            else:
                status = str(audit.get("status", "failed"))
                events.append(self._event(turn, "tool.failed", {
                    "requestId": request_id,
                    "tool": tool,
                    "code": f"tool.{status}",
                    "message": str(audit.get("message", status)),
                }))

        events.extend([
            self._event(turn, "assistant.text.started", {}),
            self._event(turn, "assistant.text.completed", {
                "text": turn.reply_text,
                "reasoning": turn.reasoning or "",
                "segments": [
                    {
                        "text": str(segment.get("text", "")),
                        "emotion": str(segment.get("emotion", "neutral")),
                        "behavior": str(segment.get("behavior", "")),
                    }
                    for segment in turn.segments
                ],
            }),
        ])

        if turn.audio:
            events.extend([
                self._event(turn, "tts.started", {
                    "format": "wav",
                    "audioSequence": 0,
                }),
                self._event(turn, "tts.audio", {
                    "data": base64.b64encode(turn.audio).decode("ascii"),
                    "format": "wav",
                    "audioSequence": 0,
                    "volumes": [],
                }),
                self._event(turn, "tts.completed", {"reason": "complete"}),
            ])
        else:
            tts_failure = next(
                (
                    warning.partition(":")[2]
                    for warning in turn.warnings
                    if warning.startswith("tts.failed:")
                ),
                "",
            )
            if tts_failure:
                events.append(self._event(turn, "tts.failed", {
                    "code": "tts.unavailable",
                    "message": tts_failure,
                }))

        plan = turn.output.performance
        events.extend([
            self._event(turn, "character.intent", {
                "emotion": plan.emotion,
                "behavior": plan.behavior,
                "intensity": plan.intensity,
                "attention": plan.attention,
                "energy": plan.energy,
                "durationMs": plan.duration_ms,
                "contextTags": list(plan.context_tags),
                "motionPlan": plan.motion_plan,
            }),
            self._event(turn, "turn.completed", {"reason": "complete"}),
            DomainEvent.create(
                "runtime.status",
                {"state": "idle", "message": ""},
            ),
        ])
        return events

    def emit(self, turn: CharacterTurn) -> list[DomainEvent]:
        return [*self.start(turn), *self.emit_completion(turn)]
