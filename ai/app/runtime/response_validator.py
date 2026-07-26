"""Normalize model presentation output before TTS and memory."""

from dataclasses import dataclass

from app.runtime.character_intent import BEHAVIORS, EMOTIONS


@dataclass
class ValidatedResponse:
    reply: str
    segments: list[dict]
    valid: bool = True


class ResponseValidator:
    def validate(self, reply: str, segments: list[dict] | None) -> ValidatedResponse:
        malformed_structured = bool(
            reply and str(reply).lstrip().startswith(("{", "["))
            and not segments
        )
        normalized = []
        for raw in segments or []:
            text = str(raw.get("text", "")).strip()
            if not text:
                continue
            emotion = str(raw.get("emotion", "neutral")).lower()
            behavior = str(raw.get("behavior", "speak")).lower()
            if emotion not in EMOTIONS:
                emotion = "neutral"
            if behavior not in BEHAVIORS or behavior == "idle":
                behavior = "speak"
            item = dict(raw)
            item.update({
                "text": text,
                "emotion": emotion,
                "behavior": behavior,
                "energy": self._clamp(raw.get("energy", 0.5)),
                "intensity": self._clamp(raw.get("intensity", 0.5)),
            })
            normalized.append(item)
        if normalized:
            reply = " ".join(item["text"] for item in normalized)
        elif reply:
            reply = str(reply).strip()
            if reply.startswith(("{", "[")):
                reply = "I couldn't format that response safely."
            normalized = [{
                "text": reply, "emotion": "neutral",
                "behavior": "speak", "attention": "user",
                "energy": 0.5, "intensity": 0.5,
            }]
        return ValidatedResponse(
            str(reply or "").strip(), normalized, not malformed_structured
        )

    @staticmethod
    def _clamp(value) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.5
