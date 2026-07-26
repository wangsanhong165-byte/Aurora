"""Initiative candidates and the runtime-owned, deduplicating queue."""

from __future__ import annotations

import hashlib
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

_SPACE_RE = re.compile(r"\s+")


def topic_fingerprint(topic: str) -> str:
    normalized = _SPACE_RE.sub(" ", topic.strip().casefold())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class InitiativeCandidate:
    candidate_id: str
    source: str
    topic: str
    topic_fingerprint: str
    priority: float
    freshness: float
    ttl_seconds: float
    created_at: float
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        source: str,
        topic: str,
        priority: float,
        freshness: float = 1.0,
        ttl_seconds: float = 300.0,
        created_at: float | None = None,
        payload: dict[str, Any] | None = None,
    ) -> "InitiativeCandidate":
        created = time.time() if created_at is None else created_at
        fingerprint = topic_fingerprint(topic)
        identity = f"{source}:{fingerprint}:{created:.6f}"
        return cls(
            candidate_id=hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24],
            source=source,
            topic=topic.strip(),
            topic_fingerprint=fingerprint,
            priority=max(0.0, min(1.0, float(priority))),
            freshness=max(0.0, min(1.0, float(freshness))),
            ttl_seconds=max(0.0, float(ttl_seconds)),
            created_at=created,
            payload=dict(payload or {}),
        )

    def expired(self, now: float) -> bool:
        return now > self.created_at + self.ttl_seconds


class InitiativeQueue:
    """Thread-safe queue owned by CharacterRuntime."""

    def __init__(self) -> None:
        self._items: dict[str, InitiativeCandidate] = {}
        self._lock = threading.Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def enqueue(self, candidate: InitiativeCandidate) -> None:
        with self._lock:
            current = self._items.get(candidate.topic_fingerprint)
            if current is None or (
                candidate.priority,
                candidate.freshness,
                candidate.created_at,
            ) >= (
                current.priority,
                current.freshness,
                current.created_at,
            ):
                self._items[candidate.topic_fingerprint] = candidate

    def pop_next(
        self,
        *,
        now: float | None = None,
        runtime_idle: bool = True,
    ) -> InitiativeCandidate | None:
        if not runtime_idle:
            return None
        current_time = time.time() if now is None else now
        with self._lock:
            self._items = {
                key: value
                for key, value in self._items.items()
                if not value.expired(current_time)
            }
            if not self._items:
                return None
            best = max(
                self._items.values(),
                key=lambda item: (
                    item.priority,
                    item.freshness,
                    item.created_at,
                ),
            )
            del self._items[best.topic_fingerprint]
            return best
