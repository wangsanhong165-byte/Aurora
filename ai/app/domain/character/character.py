"""Character aggregate — the identity center of the system."""

from app.domain.character.persona import Persona
from app.domain.character.emotion import EmotionState
from app.domain.character.relationship import RelationshipTracker
from app.domain.character.mood import MoodTrend
from app.domain.character.goal import GoalTracker
from app.domain.character.preference import PreferenceTracker


class Character:
    """Character aggregate — combines persona, emotion, relationship, mood, goals, and preferences.

    Every interaction is Character.respond(context), making Character the
    identity center of the system.
    """

    def __init__(self, card: dict):
        self.id = card.get("id", "")
        self.persona = Persona(card)
        self.emotion = EmotionState()
        self.relationship = RelationshipTracker()
        self.mood = MoodTrend()
        self.goals = GoalTracker()
        self.preferences = PreferenceTracker()
        self._raw_card = card

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "persona": {
                "name": self.persona.name,
                "setting": self.persona.setting,
            },
            "emotion": self.emotion.to_dict(),
            "relationship": self.relationship.to_dict(),
            "mood": self.mood.to_dict(),
            "goals": self.goals.to_dict(),
            "preferences": self.preferences.to_dict(),
        }

    @property
    def raw_card(self) -> dict:
        """Access the original card data for backward compatibility."""
        return self._raw_card
