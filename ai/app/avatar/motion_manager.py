# Motion Manager — manages gesture/motion playback with priority queue
# Supports idle (looping), gesture (one-shot), and special action categories.

from dataclasses import dataclass, field
import time
import logging

logger = logging.getLogger("avatar.motion")


@dataclass
class MotionDef:
    """Definition of a motion/gesture."""
    name: str
    priority: int = 50
    duration_ms: int = 500
    loop: bool = False
    category: str = "gesture"     # "idle" | "gesture" | "special"
    motion_file: str = ""         # .motion3.json file name

    @classmethod
    def from_config(cls, name: str, cfg: dict) -> "MotionDef":
        return cls(
            name=name,
            priority=cfg.get("priority", 50),
            duration_ms=cfg.get("duration_ms", 500),
            loop=cfg.get("loop", False),
            category=cfg.get("category", "gesture"),
            motion_file=cfg.get("motion_file", ""),
        )


@dataclass
class MotionState:
    """Current motion playback state."""
    name: str = "idle"
    controller: str = "IDLE"
    priority: int = 10
    started_at: float = 0.0
    duration_ms: int = 0
    loop: bool = False

    @property
    def elapsed_ms(self) -> float:
        return (time.time() - self.started_at) * 1000

    @property
    def is_finished(self) -> bool:
        if self.loop or self.duration_ms == 0:
            return False
        return self.elapsed_ms >= self.duration_ms


class MotionManager:
    """Manages motion/gesture playback with priority-based queue.

    Categories:
    - idle: looping idle animations, lowest priority, interrupted by anything
    - gesture: one-shot gestures (wave, nod, tilt), medium priority
    - special: high-priority special actions, interrupt everything lower

    Only one motion plays at a time (exclusive). Gestures and specials
    auto-return to idle when finished.
    """

    def __init__(self):
        self._defs: dict[str, MotionDef] = {}
        self._state = MotionState()
        self._queue: list[str] = []
        self._idle_motion = "idle"

    def register(self, name: str, motion: MotionDef) -> None:
        self._defs[name] = motion
        if motion.category == "idle":
            self._idle_motion = name

    def register_all(self, motions: dict[str, dict]) -> None:
        for name, cfg in motions.items():
            self.register(name, MotionDef.from_config(name, cfg))

    def play(self, name: str, source: str, priority: int) -> bool:
        """Play a motion by name. Returns False if motion not found."""
        motion = self._defs.get(name)
        if motion is None:
            logger.warning("Motion '%s' not found", name)
            return False

        self._state = MotionState(
            name=name,
            controller=source,
            priority=priority,
            started_at=time.time(),
            duration_ms=motion.duration_ms,
            loop=motion.loop,
        )
        logger.info("Motion → %s (by %s, priority=%d, loop=%s)", name, source, priority, motion.loop)
        return True

    def stop(self) -> None:
        """Stop current motion and return to idle."""
        self._state = MotionState(
            name=self._idle_motion,
            controller="IDLE",
            priority=10,
            started_at=time.time(),
            loop=True,
        )
        self._queue.clear()

    def enqueue(self, name: str) -> None:
        """Queue a motion to play after current one finishes."""
        self._queue.append(name)

    def clear_queue(self) -> None:
        self._queue.clear()

    def update(self) -> MotionState | None:
        """Call periodically. Returns new state if auto-return to idle occurred."""
        if self._state.is_finished:
            # Check queue first
            if self._queue:
                next_name = self._queue.pop(0)
                self.play(next_name, "SYSTEM", 80)
                return self._state
            # Return to idle
            self.play(self._idle_motion, "IDLE", 10)
            return self._state
        return None

    def get_current(self) -> MotionState:
        return self._state

    def get_def(self, name: str) -> MotionDef | None:
        return self._defs.get(name)

    def list_motions(self) -> list[str]:
        return list(self._defs.keys())

    @property
    def idle_motion(self) -> str:
        return self._idle_motion
