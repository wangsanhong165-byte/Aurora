"""Central state store — shared singleton across all modules.

Moved from app.runtime.state_store to break the circular import chain:
  app.input.manager → app.core.state → app.runtime.state_store
  → app.runtime.__init__ → app.runtime.runtime → app.core.state

Now app.core.state imports from app.core.state_store (same package level),
eliminating the runtime dependency in the foundational layer.
"""

from threading import RLock


class StateStore:
    """Thread-safe global state store.

    Centralizes all runtime state to prevent fragmentation across modules.
    """

    def __init__(self):
        self._state: dict = {}
        self._lock = RLock()

    def get(self, key: str, default=None):
        with self._lock:
            return self._state.get(key, default)

    def set(self, key: str, value) -> None:
        with self._lock:
            self._state[key] = value

    def update(self, **changes) -> None:
        with self._lock:
            self._state.update(changes)

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._state)


state_store = StateStore()
