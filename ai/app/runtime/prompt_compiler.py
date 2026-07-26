"""Pure prompt compilation for a CharacterTurn."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from app.runtime.character_turn import CharacterTurn


@dataclass(frozen=True)
class CompiledPrompt:
    messages: list[dict[str, Any]]


class PromptCompiler:
    """Compile model messages without executing tools or mutating the turn."""

    def __init__(self, planner: Any):
        self._planner = planner

    def compile(
        self,
        turn: CharacterTurn,
        character_self: Any,
    ) -> CompiledPrompt:
        # character_self is an explicit input even while the existing planner
        # reads turn.character during the migration.
        del character_self
        plan = self._planner.plan(turn)
        return CompiledPrompt(messages=deepcopy(list(plan.messages)))
