"""Character emotion state."""


class EmotionState:
    """Tracks the character's current emotional state."""

    VALID_EMOTIONS = {
        # Universal basics
        "neutral", "happy", "sad", "angry", "surprised",
        "worried", "shy", "gentle", "serious", "jealous",
        # Character-specific emotion words
        "playful", "explaining", "smile", "cheerful",
        "cold", "stern", "emphasizing", "happy_closed",
        "laughing", "awkward_smile", "awkward", "nervous",
        "shocked", "sigh", "giving_up", "warm_smile",
        "friendly", "curious", "cold_stare", "meek",
        "soft_smile", "blank", "thinking", "lightly_surprised",
        "confused", "blissful", "joyful", "awkward_grin",
        "embarrassed", "startled", "panicked",
        # Emotions CharacterIntent.EMOTIONS accepts but the durable state was
        # missing, so LLM-expressed ones used to be force-downgraded to neutral.
        "calm", "love", "cry", "pout", "dizzy", "sleepy", "crying", "blushing",
    }

    def __init__(self, initial: str = "neutral"):
        self.current = initial if initial in self.VALID_EMOTIONS else "neutral"
        self._intensity: float = 0.5
        self._history: list[dict] = []

    @property
    def intensity(self) -> float:
        return self._intensity

    def to_dict(self) -> dict:
        return {
            "current": self.current,
            "intensity": self._intensity,
        }
