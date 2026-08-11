"""Canonical normalization for renderer-independent performance plans.

The LLM boundary is tolerant of harmless metadata, while the executable
semantic plan remains small, bounded and renderer-free.  Every runtime path
uses this module before a plan reaches the typed transport contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


MOTION_PRIMITIVES = frozenset({
    "nod", "tilt_left", "tilt_right", "lean_forward", "lean_back",
    "sway", "look_left", "look_right", "breathe", "shrug",
})
MAX_MOTION_STEPS = 3


@dataclass(frozen=True)
class MotionPlanNormalization:
    plan: dict[str, Any] | None
    warnings: tuple[str, ...] = ()


def normalize_motion_plan(value: Any) -> MotionPlanNormalization:
    """Return the safe executable subset of a semantic motion plan.

    A malformed step is removed without discarding valid siblings. Renderer
    fields invalidate the containing step (or the whole plan when present at
    the envelope level); unknown descriptive metadata is simply omitted.
    """
    if value is None:
        return MotionPlanNormalization(None)
    if not isinstance(value, dict):
        return MotionPlanNormalization(None, ("motion_plan_removed",))
    if any(_is_renderer_key(key) for key in value if key not in {"durationMs", "steps"}):
        return MotionPlanNormalization(None, ("motion_plan_renderer_details_removed",))

    duration = _finite_number(value.get("durationMs"))
    steps = value.get("steps")
    if duration is None or not 300 <= duration <= 8000 or not isinstance(steps, list):
        return MotionPlanNormalization(None, ("motion_plan_removed",))

    warnings: list[str] = []
    if any(key not in {"durationMs", "steps"} for key in value):
        warnings.append("motion_plan_metadata_removed")
    normalized_steps: list[dict[str, Any]] = []
    for raw_step in steps:
        step = _normalize_step(raw_step, duration)
        if step is None:
            warnings.append("motion_plan_step_removed")
            continue
        if len(normalized_steps) >= MAX_MOTION_STEPS:
            warnings.append("motion_plan_truncated")
            continue
        if any(key not in {"atMs", "durationMs", "primitive", "intensity"} for key in raw_step):
            warnings.append("motion_plan_metadata_removed")
        normalized_steps.append(step)

    if not normalized_steps:
        warnings.append("motion_plan_removed")
        return MotionPlanNormalization(None, tuple(dict.fromkeys(warnings)))
    return MotionPlanNormalization(
        {"durationMs": int(duration), "steps": normalized_steps},
        tuple(dict.fromkeys(warnings)),
    )


def _normalize_step(value: Any, plan_duration: float) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    extra_keys = set(value) - {"atMs", "durationMs", "primitive", "intensity"}
    if any(_is_renderer_key(key) for key in extra_keys):
        return None
    at_ms = _finite_number(value.get("atMs"))
    duration_ms = _finite_number(value.get("durationMs"))
    intensity = _finite_number(value.get("intensity"))
    primitive = value.get("primitive")
    if (
        at_ms is None
        or duration_ms is None
        or intensity is None
        or primitive not in MOTION_PRIMITIVES
        or at_ms < 0
        or not 120 <= duration_ms <= 2500
        or not 0 <= intensity <= 1
        or at_ms + duration_ms > plan_duration
    ):
        return None
    return {
        "atMs": int(at_ms),
        "durationMs": int(duration_ms),
        "primitive": str(primitive),
        "intensity": float(intensity),
    }


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if number == number and number not in {float("inf"), float("-inf")} else None


def _is_renderer_key(key: Any) -> bool:
    normalized = str(key).casefold()
    return (
        normalized.startswith(("param", "cubism"))
        or normalized in {"parameter", "parameters", "keyframe", "keyframes", "expression", "motion", "model", "model_id"}
        or normalized.endswith((".exp3", ".model3", ".motion3"))
    )
