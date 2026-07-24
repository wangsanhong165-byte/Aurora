# Avatar State — persistent save/restore for character appearance and expression
# Saves to data/avatar_state.json; restored on connection.

from dataclasses import dataclass, asdict, field
import json
import os
import time
import logging

logger = logging.getLogger("avatar.state")


@dataclass
class AvatarState:
    """Complete snapshot of avatar visual state for persistence."""
    components: dict[str, bool] = field(default_factory=dict)
    expression: str = "neutral"
    expression_intensity: float = 1.0
    motion: str = "idle"
    model_id: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AvatarState":
        return cls(
            components=data.get("components", {}),
            expression=data.get("expression", "neutral"),
            expression_intensity=data.get("expression_intensity", 1.0),
            motion=data.get("motion", "idle"),
            model_id=data.get("model_id", ""),
            timestamp=data.get("timestamp", time.time()),
        )


class AvatarStateStore:
    """Persists and restores AvatarState to/from disk."""

    def __init__(self, data_dir: str | None = None):
        if data_dir is None:
            data_dir = os.environ.get(
                "AVATAR_STATE_DIR",
                os.path.join(os.path.dirname(__file__), "..", "..", "data"),
            )
        self._path = os.path.join(data_dir, "avatar_state.json")

    @property
    def path(self) -> str:
        return self._path

    def save(self, state: AvatarState) -> bool:
        """Persist state to disk. Creates directory if needed."""
        try:
            state.timestamp = time.time()
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)
            logger.info("Avatar state saved to %s", self._path)
            return True
        except OSError as e:
            logger.warning("Failed to save avatar state: %s", e)
            return False

    def load(self) -> AvatarState:
        """Load persisted state. Returns default state if file missing or corrupt."""
        try:
            if not os.path.exists(self._path):
                logger.info("No saved avatar state at %s, using defaults", self._path)
                return AvatarState()
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            state = AvatarState.from_dict(data)
            logger.info("Avatar state loaded from %s", self._path)
            return state
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load avatar state, using defaults: %s", e)
            return AvatarState()

    def delete(self) -> bool:
        """Remove persisted state file. Returns True if file was deleted or didn't exist."""
        try:
            if os.path.exists(self._path):
                os.remove(self._path)
                logger.info("Avatar state deleted: %s", self._path)
            return True
        except OSError as e:
            logger.warning("Failed to delete avatar state: %s", e)
            return False
