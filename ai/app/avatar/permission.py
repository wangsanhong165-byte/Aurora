# Permission Manager — dual-control arbitration for Human + AI avatar operations
# Enforces: USER(100) > SYSTEM(80) > AI(50) > IDLE(10)
# Higher priority wins; same source can overwrite itself.

from enum import IntEnum
from dataclasses import dataclass, field
import time
import logging

logger = logging.getLogger("avatar.permission")


class PermissionLevel(IntEnum):
    USER = 100
    SYSTEM = 80
    AI = 50
    IDLE = 10


@dataclass
class ControlEntry:
    """Tracks who currently controls a specific resource (component/expression/motion)."""
    controller: str          # "USER" | "AI" | "SYSTEM" | "IDLE"
    priority: int
    timestamp: float = field(default_factory=time.time)


class PermissionManager:
    """Arbitrates avatar control requests between Human (USER) and AI.

    Rules:
    - Higher priority always wins.
    - Same source can always overwrite its own state.
    - SYSTEM can overwrite anything (startup/state restore).
    - IDLE (blink, breath) is lowest — anything can overwrite it.
    """

    def __init__(self):
        self._controls: dict[str, ControlEntry] = {}

    def authorize(self, source: str, priority: int, resource: str) -> tuple[bool, str]:
        """Check if a request is authorized.

        Returns (allowed, reason).
        """
        current = self._controls.get(resource)

        if current is None:
            return True, "no_current_controller"

        # Same source can always overwrite itself
        if source == current.controller:
            return True, "same_source"

        # Same priority — allow if same source, deny if different
        if priority == current.priority:
            return False, f"priority_tie: {current.controller} (priority {current.priority} == {priority})"

        if priority > current.priority:
            return True, f"higher_priority ({priority} > {current.priority})"

        return False, f"denied: {current.controller} (priority {current.priority} > {priority})"

    def claim(self, source: str, priority: int, resource: str) -> None:
        """Record that a source now controls a resource."""
        self._controls[resource] = ControlEntry(
            controller=source,
            priority=priority,
        )
        logger.debug("Permission claim: %s → %s (priority=%d)", source, resource, priority)

    def release(self, resource: str) -> None:
        """Release control of a resource."""
        self._controls.pop(resource, None)
        logger.debug("Permission release: %s", resource)

    def release_all(self, source: str) -> None:
        """Release all resources controlled by a specific source."""
        to_release = [r for r, c in self._controls.items() if c.controller == source]
        for r in to_release:
            del self._controls[r]
        if to_release:
            logger.debug("Released %d resources from %s", len(to_release), source)

    def get_controller(self, resource: str) -> ControlEntry | None:
        """Get who currently controls a resource."""
        return self._controls.get(resource)

    def get_all_controls(self) -> dict[str, ControlEntry]:
        """Get all current control entries (for debug display)."""
        return dict(self._controls)

    def reset(self) -> None:
        """Clear all control state."""
        self._controls.clear()
