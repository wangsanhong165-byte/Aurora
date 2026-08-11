"""High-level character intent contract. Never contains renderer or Cubism data."""
from dataclasses import asdict, dataclass
from typing import Any

from app.runtime.semantic_performance import normalize_motion_plan

EMOTIONS = {
    "neutral", "calm", "happy", "joyful", "playful", "love", "shy",
    "embarrassed", "surprised", "confused", "worried", "sad", "cry",
    "angry", "pout", "blank", "cheerful", "smile", "laughing",
    "dizzy", "sleepy", "crying", "blushing",
}
BEHAVIORS = {"greet", "listen", "think", "speak", "agree", "disagree", "laugh", "idle", "comfort", "wave", "nod", "tilt", "shrug"}
ATTENTIONS = {"user", "screen", "away", "neutral"}
@dataclass(frozen=True)
class CharacterIntent:
    emotion: str = "neutral"
    behavior: str = ""
    intensity: float = 0.5
    attention: str = "user"
    energy: float = 0.5
    duration_ms: int | None = None
    natural_vad: dict[str, float] | None = None
    context_tags: tuple[str, ...] = ()
    motion_plan: dict[str, Any] | None = None

    @classmethod
    def from_llm_segment(cls, segment: dict[str, Any] | None, intensity: float = 0.5) -> "CharacterIntent":
        segment = segment if isinstance(segment, dict) else {}
        emotion = str(segment.get("emotion", "neutral")).lower()
        behavior = str(segment.get("behavior", "")).lower()
        attention = str(segment.get("attention", "user")).lower()
        raw_intensity = cls._bounded_float(segment.get("intensity", intensity), intensity)
        raw_energy = cls._bounded_float(segment.get("energy", raw_intensity), raw_intensity)
        duration = segment.get("durationMs")
        natural_vad = cls._natural_vad(segment.get("naturalVAD", segment.get("natural_vad")))
        raw_tags = segment.get("contextTags", segment.get("context_tags", ()))
        tags = tuple(dict.fromkeys(
            tag.strip().lower() for tag in raw_tags
            if isinstance(tag, str) and tag.strip()
        ))[:8] if isinstance(raw_tags, (list, tuple)) else ()
        return cls(
            emotion=emotion if emotion in EMOTIONS else "neutral",
            behavior=behavior if behavior in BEHAVIORS else "",
            intensity=raw_intensity,
            attention=attention if attention in ATTENTIONS else "user",
            energy=raw_energy,
            duration_ms=int(duration) if isinstance(duration, (int, float)) and not isinstance(duration, bool) and 0 < duration <= 10000 else None,
            natural_vad=natural_vad,
            context_tags=tags,
            motion_plan=cls._motion_plan(segment.get("motionPlan", segment.get("motion_plan"))),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def _natural_vad(value: Any) -> dict[str, float] | None:
        if not isinstance(value, dict):
            return None
        result: dict[str, float] = {}
        for key in ("valence", "arousal", "dominance"):
            try:
                result[key] = max(-1.0, min(1.0, float(value.get(key, 0))))
            except (TypeError, ValueError):
                result[key] = 0.0
        return result

    @staticmethod
    def _motion_plan(value: Any) -> dict[str, Any] | None:
        return normalize_motion_plan(value).plan

    @staticmethod
    def _bounded_float(value: Any, fallback: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = fallback
        if number != number or number in {float("inf"), float("-inf")}:
            number = fallback
        return max(0.0, min(1.0, number))
