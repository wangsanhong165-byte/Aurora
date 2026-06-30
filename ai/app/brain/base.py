"""Strategy base classes for the Brain module."""

from abc import ABC, abstractmethod
from typing import Any

from app.runtime.context import Context


class Plan:
    """A generated plan consisting of a message list for the LLM."""

    def __init__(self, messages: list[dict]):
        self.messages = messages


class PlannerStrategy(ABC):
    """Interface for any planning strategy.

    A strategy takes a Context and produces a Plan (message list).
    Strategies can be swapped at runtime via injectable planner parameter.
    """

    name: str = "base"

    @abstractmethod
    def plan(self, ctx: Context) -> Plan:
        ...


class PlanningStrategy(PlannerStrategy):
    """Convenience base class with plan() passthrough and metadata.

    Subclasses override plan() to implement custom prompt building.
    """

    name: str = "base"

    def __init__(self):
        self._metadata: dict[str, Any] = {}

    @abstractmethod
    def plan(self, ctx: Context) -> Plan:
        ...

    @property
    def metadata(self) -> dict:
        return dict(self._metadata)
