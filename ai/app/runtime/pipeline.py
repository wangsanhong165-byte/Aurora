"""Typed CharacterTurn pipeline infrastructure."""

from __future__ import annotations

from abc import ABC, abstractmethod
import time

from app.runtime.character_turn import CharacterTurn


class Step(ABC):
    @abstractmethod
    async def run(self, turn: CharacterTurn) -> None:
        """Mutate runtime-owned transient fields on one CharacterTurn."""


class Pipeline:
    """Run ordered steps until completion or a structured turn failure."""

    def __init__(self):
        self._steps: list[Step] = []

    def add(self, step: Step) -> "Pipeline":
        self._steps.append(step)
        return self

    async def run(self, turn: CharacterTurn) -> CharacterTurn:
        for step in self._steps:
            started_at = time.perf_counter()
            try:
                await step.run(turn)
            except Exception as exc:
                turn.fail(
                    f"pipeline.{step.__class__.__name__}",
                    str(exc),
                )
            finally:
                turn.metrics[f"{step.__class__.__name__}_ms"] = (
                    time.perf_counter() - started_at
                ) * 1000
            if turn.error:
                break
        return turn
