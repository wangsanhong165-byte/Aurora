# Component Manager — manages avatar accessory/part visibility
# Each component maps to one or more expression presets or part IDs.
# Uses expression params (Cubism "Add" blend) or PartOpacity to control visibility.

from dataclasses import dataclass, field
from typing import Any
import logging

logger = logging.getLogger("avatar.component")


@dataclass
class ComponentDef:
    """Definition of a toggleable avatar component."""
    name: str              # config key: "goggles"
    display_name: str      # display label: "护目镜"
    expression: str = ""   # .exp3.json file name (e.g. "8")
    param_ids: list[str] = field(default_factory=list)  # Cubism parameter IDs
    part_ids: list[str] = field(default_factory=list)    # Cubism PartOpacity IDs
    default_state: bool = False
    category: str = "accessory"  # "headwear" | "clothing" | "accessory"

    @classmethod
    def from_config(cls, name: str, cfg: dict) -> "ComponentDef":
        return cls(
            name=name,
            display_name=cfg.get("display_name", name),
            expression=cfg.get("expression", ""),
            param_ids=cfg.get("param_ids", []),
            part_ids=cfg.get("part_ids", []),
            default_state=cfg.get("default_state", False),
            category=cfg.get("category", "accessory"),
        )


@dataclass
class ComponentState:
    """Runtime state of a single component."""
    name: str
    enabled: bool
    controller: str        # "USER" | "AI" | "SYSTEM"
    priority: int


class ComponentManager:
    """Manages avatar component visibility and state.

    Components can be controlled via:
    1. Expression presets (param values with "Add" blend — one param per accessory)
    2. PartOpacity (drawable visibility — for models with explicit parts)

    State is tracked per-component with controller/priority for dual-control arbitration.
    """

    def __init__(self):
        self._defs: dict[str, ComponentDef] = {}
        self._states: dict[str, ComponentState] = {}

    def register(self, component: ComponentDef) -> None:
        """Register a component definition. Initializes state to default."""
        self._defs[component.name] = component
        self._states[component.name] = ComponentState(
            name=component.name,
            enabled=component.default_state,
            controller="SYSTEM",
            priority=80,
        )

    def register_all(self, components: dict[str, dict]) -> None:
        """Register multiple components from config dict."""
        for name, cfg in components.items():
            self.register(ComponentDef.from_config(name, cfg))

    def enable(self, name: str, source: str, priority: int) -> bool:
        """Enable a component. Returns False if component doesn't exist."""
        if name not in self._defs:
            logger.warning("Component '%s' not found", name)
            return False
        self._states[name] = ComponentState(
            name=name, enabled=True, controller=source, priority=priority,
        )
        logger.info("Component '%s' → ON (by %s, priority=%d)", name, source, priority)
        return True

    def disable(self, name: str, source: str, priority: int) -> bool:
        """Disable a component."""
        if name not in self._defs:
            logger.warning("Component '%s' not found", name)
            return False
        self._states[name] = ComponentState(
            name=name, enabled=False, controller=source, priority=priority,
        )
        logger.info("Component '%s' → OFF (by %s, priority=%d)", name, source, priority)
        return True

    def toggle(self, name: str, source: str, priority: int) -> bool:
        """Toggle a component on/off. Returns new state, or None if component not found."""
        if name not in self._defs:
            return False
        current = self._states[name].enabled
        if current:
            return self.disable(name, source, priority)
        else:
            return self.enable(name, source, priority)

    def is_enabled(self, name: str) -> bool:
        """Check if a component is currently enabled."""
        state = self._states.get(name)
        return state.enabled if state else False

    def get_state(self, name: str) -> ComponentState | None:
        """Get the full state of a component."""
        return self._states.get(name)

    def get_all_states(self) -> dict[str, bool]:
        """Get enabled/disabled map of all components."""
        return {name: s.enabled for name, s in self._states.items()}

    def get_all_defs(self) -> dict[str, ComponentDef]:
        """Get all component definitions."""
        return dict(self._defs)

    def get_def(self, name: str) -> ComponentDef | None:
        """Get a single component definition."""
        return self._defs.get(name)

    def list_components(self) -> list[str]:
        """List all registered component names."""
        return list(self._defs.keys())

    def reset_to_defaults(self) -> None:
        """Reset all components to their default states."""
        for name, comp in self._defs.items():
            self._states[name] = ComponentState(
                name=name,
                enabled=comp.default_state,
                controller="SYSTEM",
                priority=80,
            )

    def to_frontend_payload(self) -> dict[str, Any]:
        """Generate payload for frontend component sync.

        Returns dict with:
        - parts: label → expression name
        - state: label → enabled
        - defs: label → {display_name, category, expression, param_ids, part_ids}
        """
        parts = {}
        state = {}
        defs = {}
        for name, comp in self._defs.items():
            label = comp.display_name or name
            expression = comp.expression
            if expression:
                parts[label] = expression
            state[label] = self._states[name].enabled
            defs[label] = {
                "name": name,
                "display_name": comp.display_name,
                "category": comp.category,
                "expression": comp.expression,
                "param_ids": comp.param_ids,
                "part_ids": comp.part_ids,
            }
        return {"parts": parts, "state": state, "defs": defs}
