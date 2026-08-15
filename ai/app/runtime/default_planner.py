"""Compatibility facade for callers that still request a planner object."""

from __future__ import annotations

from copy import deepcopy

from app.runtime.character_turn import CharacterTurn
from app.runtime.prompt_compiler import PromptCompiler


class Plan:
    def __init__(self, messages: list, sources: list[str] | None = None):
        self.messages = messages
        self.sources = list(sources or [])


class DefaultPlanner:
    """Delegate legacy ``plan`` calls to the single PromptCompiler boundary."""

    def __init__(
        self,
        prompt_store=None,
        prompt_config_store=None,
        presentation_registry=None,
    ) -> None:
        self._compiler = PromptCompiler(
            prompt_store=prompt_store,
            prompt_config_store=prompt_config_store,
            presentation_registry=presentation_registry,
        )

    def plan(self, ctx: CharacterTurn) -> Plan:
        compiled = self._compiler.compile(ctx, getattr(ctx, "character_self", None))
        messages = deepcopy(compiled.messages)
        for message in messages:
            message.pop("_source_id", None)
        return Plan(messages=messages, sources=compiled.sources)
