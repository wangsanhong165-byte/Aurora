from __future__ import annotations

from typing import TYPE_CHECKING

from app.runtime.pipeline import Step
from app.runtime.character_turn import CharacterTurn

if TYPE_CHECKING:
    from app.domain.character import Character


class CharacterStep(Step):
    """Inject character state into the pipeline context."""

    def __init__(self, character: Character):
        self.character = character

    def set_character(self, character: Character) -> None:
        self.character = character

    async def run(self, ctx: CharacterTurn) -> None:
        ctx.character = self.character
        if ctx.character_self is None:
            from app.domain.character_self import CharacterSelf
            ctx.character_self = CharacterSelf(self.character)
        ctx.emotion = self.character.emotion.current
