"""Scheduler domain — timed and conditional event triggers."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4


@dataclass
class ScheduledTask:
    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    interval: float = 0.0  # seconds, 0 = one-shot
    condition: Callable[[], bool] | None = None
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())


class Scheduler:
    """Manages timed and condition-based event triggers.

    Produces events for the Runtime — does not execute them directly.
    """

    def __init__(self):
        self._tasks: dict[str, ScheduledTask] = {}
        self._running = False

    def add_task(self, name: str, interval: float = 0.0, condition: Callable[[], bool] | None = None) -> str:
        task = ScheduledTask(name=name, interval=interval, condition=condition)
        self._tasks[task.id] = task
        return task.id

    def remove_task(self, task_id: str) -> None:
        self._tasks.pop(task_id, None)

    def get_due(self) -> list[ScheduledTask]:
        """Return tasks that should fire (one-shot or periodic ready).

        In a real implementation, this would check last-run timestamps.
        """
        return list(self._tasks.values())

    @property
    def task_count(self) -> int:
        return len(self._tasks)

    def to_dict(self) -> dict:
        return {
            "running": self._running,
            "tasks": [{"id": tid, "name": t.name} for tid, t in self._tasks.items()],
        }
