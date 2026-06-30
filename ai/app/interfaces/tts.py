from abc import ABC, abstractmethod


class TTSInterface(ABC):
    """Interface for Text-to-Speech providers."""

    @abstractmethod
    async def synthesize(self, text: str, voice: str = "", **kwargs) -> bytes:
        ...

    @abstractmethod
    async def speak(self, text: str, voice: str = "", **kwargs) -> str:
        ...


class MockTTS(TTSInterface):
    """Returns silence audio for testing."""

    async def synthesize(self, text, voice="", **kwargs) -> bytes:
        return b"\x00\x00" * 16000  # 1 second silence

    async def speak(self, text, voice="", **kwargs) -> str:
        return "spoken"
