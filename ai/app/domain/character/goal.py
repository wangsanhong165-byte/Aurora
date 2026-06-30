"""Character goals and objectives."""

import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class Goal:
    """A single goal or objective for the character."""
    description: str
    priority: int = 0  # higher = more important
    deadline: float | None = None
    completed: bool = False
    created_at: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: uuid4().hex[:12])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "priority": self.priority,
            "deadline": self.deadline,
            "completed": self.completed,
            "created_at": self.created_at,
        }


class GoalTracker:
    """Tracks active and completed goals for the character."""

    def __init__(self):
        self._goals: list[Goal] = []
        self._completed: list[Goal] = []

    def add(self, description: str, priority: int = 0,
            deadline: float | None = None) -> str:
        """Add a new active goal. Returns the goal ID."""
        goal = Goal(description=description, priority=priority, deadline=deadline)
        self._goals.append(goal)
        return goal.id

    def mark_completed(self, goal_id: str) -> bool:
        """Move a goal from active to completed. Returns True if found."""
        for i, g in enumerate(self._goals):
            if g.id == goal_id:
                g.completed = True
                self._completed.append(self._goals.pop(i))
                return True
        return False

    def cancel(self, goal_id: str) -> bool:
        """Remove a goal without marking completed."""
        for i, g in enumerate(self._goals):
            if g.id == goal_id:
                self._goals.pop(i)
                return True
        return False

    @property
    def active(self) -> list[Goal]:
        return sorted(self._goals, key=lambda g: g.priority, reverse=True)

    @property
    def completed_history(self) -> list[Goal]:
        return list(self._completed)

    def top(self, n: int = 3) -> list[Goal]:
        """Return the n highest-priority active goals."""
        return self.active[:n]

    def to_dict(self) -> dict:
        return {
            "active": [g.to_dict() for g in self._goals],
            "completed": [g.to_dict() for g in self._completed],
        }
