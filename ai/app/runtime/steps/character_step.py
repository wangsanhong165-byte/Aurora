from __future__ import annotations

from typing import TYPE_CHECKING

from app.runtime.pipeline import Step
from app.runtime.context import Context

if TYPE_CHECKING:
    from app.domain.character import Character


class CharacterStep(Step):
    """Inject character state into the pipeline context."""

    def __init__(self, character: Character):
        self.character = character

    async def run(self, ctx: Context) -> None:
        ctx.state["character"] = self.character
        ctx.state["emotion"] = self.character.emotion.current
