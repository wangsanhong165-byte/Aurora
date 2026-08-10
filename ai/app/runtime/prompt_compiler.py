"""Pure prompt compilation for a CharacterTurn."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from app.runtime.character_turn import CharacterTurn


@dataclass(frozen=True)
class CompiledPrompt:
    messages: list[dict[str, Any]]
    sources: list[str]


class PromptCompiler:
    """Compile model messages without executing tools or mutating the turn."""

    def __init__(self, planner: Any):
        self._planner = planner

    def compile(
        self,
        turn: CharacterTurn,
        character_self: Any,
    ) -> CompiledPrompt:
        # CharacterSelf remains an explicit ownership input; the planner reads
        # the same aggregate through turn.character_self.
        turn.character_self = character_self
        plan = self._planner.plan(turn)
        messages = deepcopy(list(plan.messages))
        sources = list(getattr(plan, "sources", []))
        if len(sources) < len(messages):
            sources.extend("" for _ in range(len(messages) - len(sources)))
        for message, source_id in zip(messages, sources):
            if source_id:
                message["_source_id"] = source_id
        return CompiledPrompt(messages=messages, sources=sources)
