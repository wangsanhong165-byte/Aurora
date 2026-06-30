from abc import ABC, abstractmethod


class ASRInterface(ABC):
    """Interface for Automatic Speech Recognition providers."""

    @abstractmethod
    async def transcribe(self, audio: bytes, language: str = "") -> str:
        ...


class MockASR(ASRInterface):
    """Returns fixed transcription for testing."""

    async def transcribe(self, audio, language="") -> str:
        return "test transcription"
