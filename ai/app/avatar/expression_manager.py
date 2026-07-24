# Expression Manager — manages expression preset application with fade transitions
# Works with the emotion_map from live2d_models.json to resolve semantic
# emotion names to model-specific expression presets (.exp3.json files).

from dataclasses import dataclass, field
import logging

logger = logging.getLogger("avatar.expression")


@dataclass
class ExpressionDef:
    """Definition of a named expression."""
    name: str           # semantic name: "happy"
    preset: str         # model-specific preset: "zs1"
    default: bool = False

    @classmethod
    def from_config(cls, name: str, cfg: dict) -> "ExpressionDef":
        return cls(
            name=name,
            preset=cfg.get("preset", name),
            default=cfg.get("default", False),
        )


@dataclass
class ExpressionState:
    """Current expression state."""
    name: str = "neutral"           # semantic name
    preset: str = "neutral"         # model-specific preset
    intensity: float = 1.0
    controller: str = "SYSTEM"
    priority: int = 80


class ExpressionManager:
    """Manages character expressions with preset resolution and transitions.

    Does NOT directly set Cubism parameters — it resolves the preset name
    and intensity. The frontend ExpressionController performs the actual
    parameter interpolation.
    """

    def __init__(self):
        self._defs: dict[str, ExpressionDef] = {}
        self._state = ExpressionState()
        self._default_expression = "neutral"

    def register(self, name: str, expr: ExpressionDef) -> None:
        self._defs[name] = expr
        if expr.default:
            self._default_expression = name

    def register_all(self, expressions: dict[str, dict]) -> None:
        for name, cfg in expressions.items():
            self.register(name, ExpressionDef.from_config(name, cfg))

    def set(self, name: str, intensity: float, source: str, priority: int) -> ExpressionState:
        """Set expression by semantic name. Falls back to neutral if unknown."""
        expr = self._defs.get(name)
        if expr is None:
            logger.debug("Unknown expression '%s', falling back to neutral", name)
            name = self._default_expression
            expr = self._defs.get(name)
            preset = name
        else:
            preset = expr.preset

        self._state = ExpressionState(
            name=name,
            preset=preset,
            intensity=max(0.0, min(1.0, intensity)),
            controller=source,
            priority=priority,
        )
        logger.info("Expression → %s (preset=%s, intensity=%.1f, by %s)",
                     name, preset, intensity, source)
        return self._state

    def get_current(self) -> ExpressionState:
        return self._state

    def get_preset(self, name: str) -> str:
        """Resolve semantic name to model preset name."""
        expr = self._defs.get(name)
        return expr.preset if expr else name

    def get_default(self) -> str:
        return self._default_expression

    def has(self, name: str) -> bool:
        return name in self._defs

    def list_expressions(self) -> list[str]:
        return list(self._defs.keys())

    def reset(self) -> None:
        self._state = ExpressionState(
            name=self._default_expression,
            preset=self._default_expression,
            intensity=1.0,
            controller="SYSTEM",
            priority=80,
        )
