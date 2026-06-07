"""Initiative buffer 鈥?pending proactive speech tracker.

When Monika initiates conversation, the topic goes here first.
If the user responds within a window, it becomes a relationship event.
If not, it expires silently after 24 hours.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class InitiativeEntry:
    topic: str
    tts_text: str
    time: float = field(default_factory=time.time)
    answered: bool = False


class InitiativeBuffer:
    """Tracks pending proactive speech for closure and expiry.

    Lifecycle:
        push 鈫?(user responds?) 鈫?answered 鈫?drain_answered 鈫?relationship event
             鈫?(no response)   鈫?expire after 24h 鈫?removed

    IMPORTANT: drained entries are NOT MemoryCards and do NOT enter the
    vector-searchable memory. They are summarised as relationship events
    only, to prevent the model from seeing its own speech as external input.
    """

    def __init__(self) -> None:
        self._pending: list[InitiativeEntry] = []
        self._lock = threading.Lock()
        self._expiry_thread: threading.Thread | None = None
        self._running = False

    def push(self, topic: str, tts_text: str) -> None:
        """Record a new proactive speech."""
        entry = InitiativeEntry(topic=topic, tts_text=tts_text)
        with self._lock:
            self._pending.append(entry)

    def try_close(self, user_text: str, window_sec: float = 300.0) -> str | None:
        """Check if user_text is a response to the most recent unanswered initiative.

        Uses a simple heuristic: if the user typed more than 3 characters
        within the window, treat it as a response.

        Returns the topic string if closed, None otherwise.
        """
        if len(user_text) < 4:
            return None
        now = time.time()
        with self._lock:
            # Find most recent unanswered entry within window
            for entry in reversed(self._pending):
                if entry.answered:
                    continue
                if now - entry.time > window_sec:
                    continue
                entry.answered = True
                return entry.topic
        return None

    def expire(self, max_age_sec: float = 86400.0) -> int:
        """Remove unanswered entries older than max_age_sec (default 24h).

        Returns count of expired entries.
        """
        now = time.time()
        with self._lock:
            before = len(self._pending)
            self._pending = [
                e for e in self._pending
                if e.answered or (now - e.time) < max_age_sec
            ]
            return before - len(self._pending)

    def drain_answered(self) -> list[InitiativeEntry]:
        """Drain answered entries as raw InitiativeEntry objects.

        Caller should convert these to relationship events via
        relationship.add_event(). Do NOT pipe into vector-searchable
        memory, or the model will see its own speech as external input.
        """
        entries: list[InitiativeEntry] = []
        remaining: list[InitiativeEntry] = []
        with self._lock:
            for entry in self._pending:
                if entry.answered:
                    entries.append(entry)
                else:
                    remaining.append(entry)
            self._pending = remaining
        return entries

    # ---- background expiry -----------------------------------------------

    def start_expiry(self, interval_sec: float = 600.0) -> None:
        """Start background expiry thread (default: every 10 minutes)."""
        if self._running:
            return
        self._running = True
        self._expiry_thread = threading.Thread(
            target=self._expiry_loop, args=(interval_sec,), daemon=True,
        )
        self._expiry_thread.start()

    def stop_expiry(self) -> None:
        """Stop background expiry thread."""
        self._running = False

    def _expiry_loop(self, interval_sec: float) -> None:
        while self._running:
            time.sleep(interval_sec)
            if not self._running:
                break
            self.expire()

    # ---- introspection --------------------------------------------------

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    @property
    def unanswered_count(self) -> int:
        with self._lock:
            return sum(1 for e in self._pending if not e.answered)


# Global singleton
initiative_buffer = InitiativeBuffer()
