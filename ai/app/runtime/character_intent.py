"""High-level character intent contract. Never contains renderer or Cubism data."""
from dataclasses import asdict, dataclass
from typing import Any

EMOTIONS = {
    "neutral", "calm", "happy", "joyful", "playful", "love", "shy",
    "embarrassed", "surprised", "confused", "worried", "sad", "cry",
    "angry", "pout", "blank", "cheerful", "smile", "laughing",
    "dizzy", "sleepy", "crying", "blushing",
}
BEHAVIORS = {"greet", "listen", "think", "speak", "agree", "disagree", "laugh", "idle", "comfort", "wave", "nod", "tilt", "shrug"}
ATTENTIONS = {"user", "screen", "away", "neutral"}
MOTION_PRIMITIVES = {
    "nod", "tilt_left", "tilt_right", "lean_forward", "lean_back",
    "sway", "look_left", "look_right", "breathe", "shrug",
}

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
        raw_intensity = segment.get("intensity", intensity)
        raw_energy = segment.get("energy", raw_intensity)
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
            intensity=max(0.0, min(1.0, float(raw_intensity))),
            attention=attention if attention in ATTENTIONS else "user",
            energy=max(0.0, min(1.0, float(raw_energy))),
            duration_ms=int(duration) if isinstance(duration, (int, float)) and 0 < duration <= 10000 else None,
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
        if not isinstance(value, dict) or set(value) != {"durationMs", "steps"}:
            return None
        duration = value.get("durationMs")
        steps = value.get("steps")
        if (
            not isinstance(duration, (int, float))
            or isinstance(duration, bool)
            or not 300 <= duration <= 8000
            or not isinstance(steps, list)
            or not 1 <= len(steps) <= 16
        ):
            return None

        normalized_steps: list[dict[str, Any]] = []
        allowed_keys = {"atMs", "durationMs", "primitive", "intensity"}
        for step in steps:
            if not isinstance(step, dict) or set(step) != allowed_keys:
                return None
            at_ms = step.get("atMs")
            step_duration = step.get("durationMs")
            primitive = step.get("primitive")
            intensity = step.get("intensity")
            numbers = (at_ms, step_duration, intensity)
            if any(isinstance(number, bool) for number in numbers):
                return None
            if (
                not isinstance(at_ms, (int, float))
                or not isinstance(step_duration, (int, float))
                or not isinstance(intensity, (int, float))
                or primitive not in MOTION_PRIMITIVES
                or at_ms < 0
                or not 120 <= step_duration <= 2500
                or not 0 <= intensity <= 1
                or at_ms + step_duration > duration
            ):
                return None
            normalized_steps.append({
                "atMs": int(at_ms),
                "durationMs": int(step_duration),
                "primitive": str(primitive),
                "intensity": float(intensity),
            })
        return {"durationMs": int(duration), "steps": normalized_steps}
