"""Character persona — identity and setting data."""


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
    def color(self) -> str:
        return self._card.get("color", "#888888")

    @property
    def raw_card(self) -> dict:
        """Access the validated raw card for provider adapters."""
        return self._card
