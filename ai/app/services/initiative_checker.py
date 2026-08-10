"""Initiative checker — polls the initiative queue and triggers Runtime pipeline.

Event sources (screen monitor, timer, state changes, scheduler, relationship
milestones, and idle observations) push InitiativeEvent objects into the queue.
This checker drains them periodically and dispatches INITIATIVE_TRIGGERED
events through the Runtime pipeline when appropriate.

Event sources:
  - Screen changes (from ScreenWatcher)
  - Idle timeout (auto-generated when user is inactive)
  - Scheduler reminders (due tasks)
  - Long-idle observations (gentle prompts after extended inactivity)
  - Relationship milestones (affinity thresholds reached)
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from app.core.event_bus import bus
from app.core.events import EventType
from app.core.initiative_queue import InitiativeEvent, initiative_queue
from app.core.state import state_store


class InitiativeChecker:
    """Background timer that drains the initiative queue and dispatches events.

    Fires an on_initiative callback with the best candidate when the agent
    should proactively speak. The callback is typically wired to dispatch
    an InitiativeCandidate for CharacterRuntime.

    Extended with additional event sources:
      - _last_reminder_check: tracks last scheduler poll
      - _last_observation_time: tracks last idle observation
      - _relationship_milestones: tracks affinity milestone events
    """

    # Minimum seconds between idle observations (don't spam)
    _OBSERVATION_COOLDOWN = 600.0  # 10 minutes
    # Affinity milestone thresholds
    _RELATIONSHIP_MILESTONES = [0.1, 0.25, 0.5, 0.75, 0.9]

    def __init__(
        self,
        interval: float = 10.0,
        idle_threshold: float = 300.0,
        character_getter: Callable[[], Any] | None = None,
    ) -> None:
        self.interval = interval
        self.idle_threshold = idle_threshold
        self._timer: threading.Timer | None = None
        self._running = False
        self._last_interaction = time.time()
        self.on_initiative: Callable[[list[Any]], None] | None = None
        self._character_getter = character_getter
        # Extended state
        self._last_reminder_check: float = 0.0
        self._last_observation_time: float = 0.0
        self._relationship_milestones: dict[str, set[float]] = {}
        self._last_relationship_check: float = 0.0

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._schedule()

    def stop(self) -> None:
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def touch(self) -> None:
        """Mark user interaction, reset idle timer."""
        self._last_interaction = time.time()

    def _schedule(self) -> None:
        if not self._running:
            return
        self._timer = threading.Timer(self.interval, self._tick)
        self._timer.daemon = True
        self._timer.start()

    def _tick(self) -> None:
        if not self._running:
            return
        try:
            self._check()
        finally:
            self._schedule()

    def _check(self) -> None:
        """Drain the queue and decide if agent should speak.

        Extended event sources (in addition to queue):
          1. Scheduler reminders (every 60s)
          2. Long-idle observations (after 2x idle_threshold, with cooldown)
          3. Relationship milestone events (every 300s)
          4. Idle timeout (auto-generated when user is inactive)
        """
        events = initiative_queue.drain(limit=10)
        now = time.time()
        idle = now - self._last_interaction

        # 1. Scheduler reminders (check every 60s)
        if now - self._last_reminder_check >= 60.0:
            self._last_reminder_check = now
            try:
                from app.domain.scheduler.scheduler import Scheduler
                scheduler = Scheduler()
                due = scheduler.get_due()
                for task in due:
                    events.append(InitiativeEvent(
                        type="reminder",
                        payload={"task_name": task.name, "task_id": task.id},
                        priority=3,
                    ))
            except Exception:
                pass

        # 2. Long-idle observation (after 2x idle_threshold, with cooldown)
        observation_idle = idle >= self.idle_threshold * 2
        observation_cooled = now - self._last_observation_time >= self._OBSERVATION_COOLDOWN
        if observation_idle and observation_cooled and not events:
            self._last_observation_time = now
            events.append(InitiativeEvent(
                type="observation",
                payload={"idle_seconds": idle},
                priority=1,
            ))

        # 3. Relationship milestone check (every 300s)
        REL_CHECK_INTERVAL = 300.0
        if now - self._last_relationship_check >= REL_CHECK_INTERVAL:
            self._last_relationship_check = now
            try:
                character = (
                    self._character_getter()
                    if self._character_getter is not None
                    else state_store.get("character")
                )
                if character is not None and hasattr(character, "relationship"):
                    rel = character.relationship
                    affinity = rel.get_affinity()
                    uid = str(getattr(character, "id", "default"))
                    if uid not in self._relationship_milestones:
                        self._relationship_milestones[uid] = set()
                    crossed = [m for m in self._RELATIONSHIP_MILESTONES
                               if m <= affinity and m not in self._relationship_milestones[uid]]
                    for milestone in crossed:
                        self._relationship_milestones[uid].add(milestone)
                        events.append(InitiativeEvent(
                            type="relationship_milestone",
                            payload={"affinity": affinity, "milestone": milestone},
                            priority=4,
                        ))
            except Exception:
                pass

        # 4. Auto-generate idle timeout event
        if idle >= self.idle_threshold and not events:
            events.append(InitiativeEvent(
                type="idle_timeout",
                payload={"idle_seconds": idle},
                priority=1,
            ))

        if not events:
            return

        state = state_store.snapshot()
        activity = state.get("activity", "idle")
        attention = state.get("attention", "available")

        # Suppress if user is focused and events are low-priority
        max_priority = max((e.priority for e in events), default=0)
        if attention == "focused" and max_priority < 5:
            return
        if activity == "sleeping":
            return

        bus.publish(
            EventType.STATE_CHANGED,
            {"initiative_events": len(events), "max_priority": max_priority},
            source="initiative",
        )

        if self.on_initiative:
            self.on_initiative(events)
