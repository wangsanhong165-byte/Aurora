"""Brain — replaceable reasoning strategies.

The Brain module provides composable, swappable strategies that can be
injected into DecisionStep. Each strategy implements PlannerStrategy
and can be registered with the StrategyRegistry for dynamic selection.

Usage:
    from app.brain import StrategyRegistry, PlannerStrategy

    registry = StrategyRegistry()
    planner = registry.resolve("prompt")
    step = DecisionStep(llm, tools, planner=planner())
"""

from app.brain.base import PlannerStrategy, PlanningStrategy
from app.brain.registry import StrategyRegistry
from app.brain.strategies.prompt_strategy import PromptStrategy
from app.brain.strategies.reflection_strategy import ReflectionStrategy

# Module-level global registry
strategy_registry = StrategyRegistry()
strategy_registry.register("prompt", PromptStrategy)
strategy_registry.register("reflection", ReflectionStrategy)

__all__ = [
    "PlannerStrategy",
    "PlanningStrategy",
    "StrategyRegistry",
    "strategy_registry",
    "PromptStrategy",
    "ReflectionStrategy",
]
