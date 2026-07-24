# Parameter Mixer — resolves conflicts when multiple subsystems modify the same
# Cubism parameter simultaneously (e.g., lip sync + expression both write
# ParamMouthOpenY).
#
# Each subsystem registers its "owned" parameters with a priority.
# When multiple subsystems write to the same parameter, the mixer uses
# priority-weighted blending rather than last-writer-wins.
#
# Architecture:
#   LipSync ──┐
#   Blink   ──┤
#   Breath  ──┼── ParameterMixer ──→ Final parameter values
#   Express ──┤
#   Motion  ──┘

from dataclasses import dataclass, field
import logging
from typing import Any

logger = logging.getLogger("avatar.parameter_mixer")


@dataclass
class ParameterOwner:
    """Defines which subsystem owns a set of parameters."""
    name: str                # "lip_sync" | "blink" | "breath" | "expression"
    param_ids: list[str]     # ["ParamMouthOpenY"]
    priority: int            # 60, 40, 20, 30
    mask_weight: float = 1.0 # How strongly this owner contributes (0-1)


@dataclass
class ParameterValue:
    """A single parameter value from one source."""
    param_id: str            # "ParamMouthOpenY"
    value: float             # target value
    source: str              # "lip_sync" | "blink" | "breath" | "expression"
    priority: int            # source priority
    weight: float = 1.0      # blend weight for multi-source mixing


class ParameterMixer:
    """Resolves parameter conflicts using priority-weighted blending.

    Rules:
    - Each subsystem registers the parameters it "owns" with a priority.
    - If only one source writes to a parameter, its value is used directly.
    - If multiple sources write to the same parameter, values are blended
      using priority-weighted averaging.
    - A source with mask_weight=0 is effectively silent for its owned params.
    - blink has absolute priority on eye-open params when actively blinking
      (value < 0.5 means eyes are closing/closed).
    """

    def __init__(self):
        self._owners: dict[str, ParameterOwner] = {}
        # Current frame's parameter values: {param_id: [ParameterValue, ...]}
        self._frame_values: dict[str, list[ParameterValue]] = {}
        # Resolved output: {param_id: float}
        self._resolved: dict[str, float] = {}

    # ── Configuration ──────────────────────────────────────────────────

    def register_owner(self, name: str, param_ids: list[str],
                       priority: int, mask_weight: float = 1.0) -> None:
        """Register a subsystem as the owner of specific parameters."""
        self._owners[name] = ParameterOwner(
            name=name,
            param_ids=list(param_ids),
            priority=priority,
            mask_weight=mask_weight,
        )
        logger.debug("ParameterMixer: registered '%s' (priority=%d, params=%s)",
                     name, priority, param_ids)

    def register_all(self, config: dict[str, Any]) -> None:
        """Register multiple owners from avatar.yaml parameters section."""
        for name, cfg in config.items():
            self.register_owner(
                name=name,
                param_ids=cfg.get("owns", []),
                priority=cfg.get("priority", 10),
                mask_weight=cfg.get("mask_weight", 1.0),
            )

    def get_owner(self, name: str) -> ParameterOwner | None:
        """Get a registered owner by name."""
        return self._owners.get(name)

    def list_owners(self) -> list[str]:
        return list(self._owners.keys())

    # ── Per-frame value submission ─────────────────────────────────────

    def set_params(self, source: str, values: dict[str, float],
                   priority: int | None = None) -> None:
        """Submit parameter values from a source for the current frame.

        Args:
            source: Subsystem name ("lip_sync", "blink", etc.)
            values: {param_id: target_value} mapping
            priority: Override the source's registered priority.
                      If None, uses the registered owner priority.
        """
        owner = self._owners.get(source)
        src_priority = priority if priority is not None else (owner.priority if owner else 10)

        for param_id, value in values.items():
            pv = ParameterValue(
                param_id=param_id,
                value=value,
                source=source,
                priority=src_priority,
                weight=owner.mask_weight if owner else 1.0,
            )
            if param_id not in self._frame_values:
                self._frame_values[param_id] = []
            self._frame_values[param_id].append(pv)

    def reset_frame(self) -> None:
        """Clear all submitted values for the next frame."""
        self._frame_values.clear()

    # ── Resolution ─────────────────────────────────────────────────────

    def resolve(self) -> dict[str, float]:
        """Blend all submitted parameter values into final output.

        Returns {param_id: final_value}.
        """
        self._resolved = {}

        for param_id, values in self._frame_values.items():
            if len(values) == 1:
                # Single source — use directly
                self._resolved[param_id] = values[0].value
            else:
                self._resolved[param_id] = self._blend(param_id, values)

        return dict(self._resolved)

    def _blend(self, param_id: str, values: list[ParameterValue]) -> float:
        """Blend multiple values for the same parameter.

        Strategy:
        1. If blink is active (value < 0.5) on eye-open params, blink wins absolutely.
        2. Otherwise, priority-weighted average.
        3. Ties in priority: average the values.
        """
        # Absolute blink override: when eyes are closing/closed, blink wins.
        blink_values = [v for v in values if v.source == "blink"]
        if blink_values:
            # Blink active (eyes partially or fully closed)
            if any(v.value < 0.5 for v in blink_values):
                return blink_values[0].value  # Use first blink value

        # Priority-weighted blend
        total_weight = 0.0
        weighted_sum = 0.0

        for v in values:
            w = float(v.priority) * v.weight
            weighted_sum += v.value * w
            total_weight += w

        if total_weight == 0:
            return values[0].value  # fallback

        return weighted_sum / total_weight

    # ── Query ──────────────────────────────────────────────────────────

    def get_resolved(self, param_id: str) -> float | None:
        """Get the resolved value for a single parameter (after resolve())."""
        return self._resolved.get(param_id)

    def get_all_resolved(self) -> dict[str, float]:
        """Get all resolved values (after resolve())."""
        return dict(self._resolved)

    def debug_frame(self) -> dict:
        """Debug info: which sources contributed to which parameters."""
        return {
            "frame_values": {
                pid: [{"source": v.source, "value": v.value, "priority": v.priority}
                      for v in vals]
                for pid, vals in self._frame_values.items()
            },
            "resolved": dict(self._resolved),
        }
