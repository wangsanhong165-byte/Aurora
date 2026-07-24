# Natural Behavior Manager — autonomous idle behaviors (gaze, blink, breath,
# micro-movements). These run continuously at IDLE priority and yield to any
# higher-priority system via ParameterMixer.
#
# Behaviors:
#   gaze  — mouse-driven head/eye tracking (ParamAngleX/Y/Z, ParamEyeBallX/Y)
#   blink — periodic eye open/close cycle (ParamEyeLOpen, ParamEyeROpen)
#   breath — sinusoidal body expansion (ParamBreath, ParamBodyAngleX/Y)
#   idle_micro — subtle random sway (ParamBodyAngleZ, small angle offsets)
#
# All output goes through ParameterMixer; this class does NOT touch the model
# directly. Higher-priority systems (expression, lip-sync) can override any
# natural behavior parameter.

from dataclasses import dataclass, field
import logging
import time
import math
import random

logger = logging.getLogger("avatar.natural_behavior")


@dataclass
class GazeState:
    """Current gaze tracking state."""
    target_x: float = 0.0      # mouse X in normalized [-1, 1]
    target_y: float = 0.0      # mouse Y in normalized [-1, 1]
    current_x: float = 0.0     # smoothed current X
    current_y: float = 0.0     # smoothed current Y
    smoothing: float = 0.12    # lerp factor per frame
    head_factor: float = 0.6   # how much gaze moves head vs eyes
    enabled: bool = True


@dataclass
class BlinkState:
    """Blink cycle state machine."""
    phase: str = "open"           # "open" | "closing" | "closed" | "opening"
    timer: float = 0.0            # seconds elapsed in current phase
    next_blink: float = 3.0       # seconds until next blink
    open_duration: float = 0.0    # random, set per cycle
    close_duration: float = 0.05  # time to close eyes
    closed_duration: float = 0.08 # time eyes stay closed
    open_anim_duration: float = 0.1  # time to open eyes
    eye_value: float = 1.0        # 1=fully open, 0=fully closed
    enabled: bool = True
    min_interval: float = 1.5     # minimum seconds between blinks
    max_interval: float = 5.0     # maximum seconds between blinks


@dataclass
class BreathState:
    """Breathing cycle state."""
    phase: float = 0.0            # radians, advances each frame
    cycle_duration: float = 4.0   # seconds per full breath cycle
    amplitude: float = 0.15       # max parameter deviation
    enabled: bool = True


@dataclass
class IdleMicroState:
    """Idle micro-movement state."""
    phase_x: float = 0.0
    phase_y: float = 0.0
    phase_z: float = 0.0
    speed_x: float = 0.3          # radians/sec
    speed_y: float = 0.4
    speed_z: float = 0.25
    amplitude: float = 0.03       # very subtle
    enabled: bool = True


class NaturalBehaviorManager:
    """Manages autonomous idle behaviors.

    Provides per-frame parameter updates through the update() method.
    Caller is responsible for submitting these to ParameterMixer.
    All behaviors run at IDLE priority (10) — anything can override them.
    """

    PRIORITY = 10  # IDLE — lowest priority, yields to everything

    def __init__(self):
        self.gaze = GazeState()
        self.blink = BlinkState()
        self.breath = BreathState()
        self.idle_micro = IdleMicroState()

        # Initialize random blink timing
        self._schedule_next_blink()

    # ── Gaze ───────────────────────────────────────────────────────────

    def set_gaze_target(self, x: float, y: float) -> None:
        """Set mouse position in normalized [-1, 1] coordinates."""
        self.gaze.target_x = x
        self.gaze.target_y = y

    def set_gaze_enabled(self, enabled: bool) -> None:
        self.gaze.enabled = enabled

    # ── Behavior enable/disable ────────────────────────────────────────

    def set_blink_enabled(self, enabled: bool) -> None:
        self.blink.enabled = enabled

    def set_breath_enabled(self, enabled: bool) -> None:
        self.breath.enabled = enabled

    def set_idle_enabled(self, enabled: bool) -> None:
        self.idle_micro.enabled = enabled

    # ── Per-frame update ───────────────────────────────────────────────

    def update(self, dt: float) -> dict[str, float]:
        """Advance all behaviors by dt seconds.

        Returns {param_id: value} dict for submission to ParameterMixer.
        """
        params: dict[str, float] = {}

        if self.gaze.enabled:
            params.update(self._update_gaze(dt))

        if self.blink.enabled:
            params.update(self._update_blink(dt))

        if self.breath.enabled:
            params.update(self._update_breath(dt))

        if self.idle_micro.enabled:
            params.update(self._update_idle_micro(dt))

        return params

    # ── Gaze implementation ────────────────────────────────────────────

    def _update_gaze(self, dt: float) -> dict[str, float]:
        g = self.gaze
        # Smooth follow: lerp current toward target
        g.current_x += (g.target_x - g.current_x) * min(g.smoothing * 60, dt * 60)
        g.current_y += (g.target_y - g.current_y) * min(g.smoothing * 60, dt * 60)

        head_angle = g.current_x * 30.0 * g.head_factor    # ±30 degrees max
        head_angle_y = g.current_y * 15.0 * g.head_factor  # ±15 degrees max
        eye_angle = g.current_x * (1.0 - g.head_factor)    # remainder to eyes

        return {
            "ParamAngleX": head_angle,
            "ParamAngleY": head_angle_y,
            "ParamAngleZ": g.current_x * 5.0,  # subtle tilt
            "ParamEyeBallX": eye_angle,
            "ParamEyeBallY": g.current_y * (1.0 - g.head_factor),
        }

    # ── Blink implementation ───────────────────────────────────────────

    def _update_blink(self, dt: float) -> dict[str, float]:
        b = self.blink
        b.timer += dt

        if b.phase == "open":
            # Wait for next blink
            if b.timer >= b.next_blink:
                b.phase = "closing"
                b.timer = 0.0
                b.close_duration = 0.04 + random.random() * 0.04  # 40-80ms

        elif b.phase == "closing":
            t = b.timer / b.close_duration if b.close_duration > 0 else 1.0
            b.eye_value = 1.0 - t  # 1 → 0
            if t >= 1.0:
                b.phase = "closed"
                b.timer = 0.0
                b.eye_value = 0.0
                b.closed_duration = 0.04 + random.random() * 0.06  # 40-100ms

        elif b.phase == "closed":
            b.eye_value = 0.0
            if b.timer >= b.closed_duration:
                b.phase = "opening"
                b.timer = 0.0
                b.open_anim_duration = 0.08 + random.random() * 0.08  # 80-160ms

        elif b.phase == "opening":
            t = b.timer / b.open_anim_duration if b.open_anim_duration > 0 else 1.0
            b.eye_value = t  # 0 → 1
            if t >= 1.0:
                b.phase = "open"
                b.timer = 0.0
                b.eye_value = 1.0
                self._schedule_next_blink()

        return {
            "ParamEyeLOpen": b.eye_value,
            "ParamEyeROpen": b.eye_value,
        }

    def _schedule_next_blink(self) -> None:
        b = self.blink
        b.next_blink = b.min_interval + random.random() * (b.max_interval - b.min_interval)

    # ── Breath implementation ──────────────────────────────────────────

    def _update_breath(self, dt: float) -> dict[str, float]:
        br = self.breath
        br.phase += (2.0 * math.pi / br.cycle_duration) * dt
        if br.phase > 2.0 * math.pi:
            br.phase -= 2.0 * math.pi

        wave = math.sin(br.phase) * br.amplitude
        return {
            "ParamBreath": 0.5 + wave * 0.5,  # 0-1 range, centered at 0.5
            "ParamBodyAngleX": wave * 0.3,
            "ParamBodyAngleY": wave * 0.2,
        }

    # ── Idle micro-movement implementation ─────────────────────────────

    def _update_idle_micro(self, dt: float) -> dict[str, float]:
        im = self.idle_micro
        im.phase_x += im.speed_x * dt
        im.phase_y += im.speed_y * dt
        im.phase_z += im.speed_z * dt

        return {
            "ParamBodyAngleZ": math.sin(im.phase_z) * im.amplitude,
            "ParamAngleX_offset": math.sin(im.phase_x) * im.amplitude * 0.5,
            "ParamAngleY_offset": math.cos(im.phase_y) * im.amplitude * 0.5,
        }

    # ── Snapshot for state persistence ─────────────────────────────────

    def get_enabled_state(self) -> dict[str, bool]:
        return {
            "gaze": self.gaze.enabled,
            "blink": self.blink.enabled,
            "breath": self.breath.enabled,
            "idle_micro": self.idle_micro.enabled,
        }

    def set_enabled_state(self, state: dict[str, bool]) -> None:
        if "gaze" in state:
            self.gaze.enabled = state["gaze"]
        if "blink" in state:
            self.blink.enabled = state["blink"]
        if "breath" in state:
            self.breath.enabled = state["breath"]
        if "idle_micro" in state:
            self.idle_micro.enabled = state["idle_micro"]
