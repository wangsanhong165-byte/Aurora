"""BaseASR — abstract interface for all ASR engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseASR(ABC):
    """Every ASR engine implements this."""

    engine_name: str = ""  # matches ASR_ENGINE env value

    @abstractmethod
    def transcribe(self, audio_path: str, language: str | None = None) -> dict[str, Any]:
        """Return dict with keys `text` and optionally `language`."""
        ...
