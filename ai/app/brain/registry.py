"""StrategyRegistry — dynamic strategy lookup for the Brain module."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.brain.base import PlannerStrategy


class StrategyRegistry:
    """Registry for discoverable planning strategies.

    Strategies are registered by name and resolved at runtime.
    The companion app can select strategies by name without importing
    strategy classes directly.
    """

    def __init__(self):
        self._strategies: dict[str, type["PlannerStrategy"]] = {}

    def register(self, name: str,
                 strategy_class: type["PlannerStrategy"]) -> None:
        """Register a strategy class under a given name."""
        self._strategies[name] = strategy_class

    def resolve(self, name: str) -> type["PlannerStrategy"] | None:
        """Look up a strategy class by name. Returns None if not found."""
        return self._strategies.get(name)

    def list_strategies(self) -> list[str]:
        """Return all registered strategy names."""
        return list(self._strategies.keys())

    def unregister(self, name: str) -> None:
        """Remove a strategy from the registry."""
        self._strategies.pop(name, None)
