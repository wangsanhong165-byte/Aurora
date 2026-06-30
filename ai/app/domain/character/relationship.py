"""Character relationship tracking."""


class RelationshipTracker:
    """Tracks character relationships and affinity with users."""

    def __init__(self):
        self._affinity: dict[str, float] = {}
        self._interaction_count: dict[str, int] = {}

    def get_affinity(self, user_id: str = "default") -> float:
        return self._affinity.get(user_id, 0.5)

    def update_affinity(self, delta: float, user_id: str = "default") -> None:
        current = self._affinity.get(user_id, 0.5)
        self._affinity[user_id] = max(0.0, min(1.0, current + delta))
        self._interaction_count[user_id] = self._interaction_count.get(user_id, 0) + 1

    def interaction_count(self, user_id: str = "default") -> int:
        return self._interaction_count.get(user_id, 0)

    def to_dict(self) -> dict:
        return {
            "affinity": dict(self._affinity),
            "interaction_count": dict(self._interaction_count),
        }
