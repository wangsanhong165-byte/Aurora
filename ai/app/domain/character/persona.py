"""Character persona — stable identity, setting, and structured tendencies."""

from app.domain.character.personality_profile import PersonalityProfile


class Persona:
    """Character identity and background setting.

    Wraps the character card data with domain-specific accessors.
    """

    def __init__(self, card: dict):
        self._card = card

    @property
    def id(self) -> str:
        return self._card.get("id", "")

    @property
    def name(self) -> dict:
        return self._card.get("name", {})

    @property
    def display_name(self) -> str:
        names = self.name
        return names.get("zh") or names.get("ja") or names.get("en") or self.id

    @property
    def setting(self) -> str:
        return self._card.get("character_setting") or self._card.get("system_prompt", "")

    @property
    def profile(self) -> PersonalityProfile:
        return PersonalityProfile.from_card(self._card)

    @property
    def prompt_context(self) -> str:
        """Return stable identity context without learned user state."""
        parts = []
        if self.display_name:
            parts.append(f"You are {self.display_name}.")
        if self.setting:
            parts.append(self.setting)
        structured = self.profile.to_prompt()
        if structured:
            parts.append(structured)
        return "\n".join(parts)

    @property
    def color(self) -> str:
        return self._card.get("color", "#888888")

    @property
    def raw_card(self) -> dict:
        """Access the validated raw card for provider adapters."""
        return self._card
