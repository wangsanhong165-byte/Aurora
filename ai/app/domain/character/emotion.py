"""Character emotion state."""


class Emotion:
    """An emotion state with intensity."""

    def __init__(self, name: str = "neutral", intensity: float = 0.5):
        self.name = name
        self.intensity = max(0.0, min(1.0, intensity))

    def to_dict(self) -> dict:
        return {"name": self.name, "intensity": self.intensity}


class EmotionState:
    """Tracks the character's current emotional state."""

    VALID_EMOTIONS = {
        # Universal basics
        "neutral", "happy", "sad", "angry", "surprised",
        "worried", "shy", "gentle", "serious", "jealous",
        # Monika tone words
        "playful", "explaining", "smile", "cheerful",
        "cold", "stern", "emphasizing", "happy_closed",
        "laughing", "awkward_smile", "awkward", "nervous",
        "shocked", "sigh", "giving_up", "warm_smile",
        "friendly", "curious", "cold_stare", "meek",
        "soft_smile", "blank", "thinking", "lightly_surprised",
        "confused", "blissful", "joyful", "awkward_grin",
        "embarrassed", "startled", "panicked",
    }

    def __init__(self, initial: str = "neutral"):
        self.current = initial if initial in self.VALID_EMOTIONS else "neutral"
        self._intensity: float = 0.5
        self._history: list[dict] = []

    def set(self, emotion: str, intensity: float = 0.5) -> None:
        if emotion not in self.VALID_EMOTIONS:
            emotion = "neutral"
        self._history.append({
            "from": self.current,
            "to": emotion,
            "intensity": intensity,
        })
        self.current = emotion
        self._intensity = max(0.0, min(1.0, intensity))

    @property
    def intensity(self) -> float:
        return self._intensity

    @property
    def history(self) -> list[dict]:
        return list(self._history)

    def to_dict(self) -> dict:
        return {
            "current": self.current,
            "intensity": self._intensity,
        }
