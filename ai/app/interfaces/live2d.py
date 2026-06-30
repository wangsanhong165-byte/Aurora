from abc import ABC, abstractmethod


class Live2DInterface(ABC):
    """Interface for Live2D character rendering."""

    @abstractmethod
    async def set_expression(self, emotion: str, intensity: float = 0.5) -> None:
        ...

    @abstractmethod
    async def set_gesture(self, gesture: str) -> None:
        ...

    @abstractmethod
    async def speak(self, audio: bytes, expression: str) -> None:
        ...


class MockLive2D(Live2DInterface):
    """No-op implementation for testing."""

    async def set_expression(self, emotion, intensity=0.5):
        pass

    async def set_gesture(self, gesture):
        pass

    async def speak(self, audio, expression):
        pass
