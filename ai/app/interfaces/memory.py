from abc import ABC, abstractmethod
from typing import Any


class MemoryInterface(ABC):
    """Interface for memory storage and retrieval.

    Lifecycle:
        start(character_registry, llm_provider) — called by Runtime after
            construction to initialize background tasks (ticker, store).
        shutdown() — called to stop background tasks gracefully.
    """

    @abstractmethod
    def start(self, character_registry: Any = None, llm_provider: Any = None) -> None:
        """Initialize background memory tasks (store, ticker, compiler).

        Called once by Runtime after all providers are resolved.
        Implementations should start background threads here.
        """
        ...

    @abstractmethod
    async def store(self, event_type: str, data: dict) -> None:
        ...

    @abstractmethod
    async def retrieve(self, query: str, limit: int = 10, **context) -> list[dict]:
        ...

    @abstractmethod
    async def consolidate(self) -> None:
        ...

    @abstractmethod
    async def summarize(self, since: str) -> str:
        ...

    @abstractmethod
    async def forget(self, before: str) -> int:
        ...

    @abstractmethod
    def shutdown(self) -> None:
        """Stop background tasks gracefully.

        Called once by Runtime during shutdown.
        Implementations should stop threads and close connections here.
        """
        ...

    @abstractmethod
    def notify_turn(self) -> None:
        """Signal that a conversation turn has been processed.

        Called by Runtime.dispatch() after each successful pipeline run.
        Implementations use this to trigger periodic background work
        (e.g., fact extraction, memory compilation) without Runtime
        knowing about their internal scheduler.
        """
        ...


class MockMemory(MemoryInterface):
    """In-memory mock for testing."""

    def __init__(self):
        self._storage: list[dict] = []

    def start(self, character_registry: Any = None, llm_provider: Any = None) -> None:
        pass

    async def store(self, event_type: str, data: dict) -> None:
        self._storage.append({"event_type": event_type, "data": data})

    async def retrieve(self, query: str, limit: int = 10, **context) -> list[dict]:
        return self._storage[-limit:]

    async def consolidate(self) -> None:
        pass

    async def summarize(self, since: str) -> str:
        return f"Mock summary: {len(self._storage)} events."

    async def forget(self, before: str) -> int:
        count = len(self._storage)
        self._storage.clear()
        return count

    def shutdown(self) -> None:
        pass

    def notify_turn(self) -> None:
        pass
