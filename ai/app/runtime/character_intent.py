"""High-level character intent contract. Never contains renderer or Cubism data."""
from dataclasses import asdict, dataclass
from typing import Any

EMOTIONS = {"neutral", "happy", "sad", "angry", "surprised", "confused", "shy", "love"}
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

    @classmethod
    def from_llm_segment(cls, segment: dict[str, Any] | None, intensity: float = 0.5) -> "CharacterIntent":
        segment = segment if isinstance(segment, dict) else {}
        emotion = str(segment.get("emotion", segment.get("tone", "neutral"))).lower()
        behavior = str(segment.get("behavior", segment.get("gesture", ""))).lower()
        attention = str(segment.get("attention", "user")).lower()
        raw_intensity = segment.get("intensity", intensity)
        raw_energy = segment.get("energy", raw_intensity)
        duration = segment.get("durationMs")
        return cls(
            emotion=emotion if emotion in EMOTIONS else "neutral",
            behavior=behavior if behavior in BEHAVIORS else "",
            intensity=max(0.0, min(1.0, float(raw_intensity))),
            attention=attention if attention in ATTENTIONS else "user",
            energy=max(0.0, min(1.0, float(raw_energy))),
            duration_ms=int(duration) if isinstance(duration, (int, float)) and 0 < duration <= 10000 else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
