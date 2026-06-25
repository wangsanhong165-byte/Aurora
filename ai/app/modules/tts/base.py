"""BaseTTS -- abstract interface for all TTS engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.core.schemas import TTSResponse


class BaseTTS(ABC):
    """Every TTS engine implements this.

    - `synthesize(text, **options)` → raw WAV bytes (used for playback)
    - `speak(text, **options)` → TTSResponse (used for status/UI)
    """

    engine_name: str = ""  # override in subclass, matches TTS_ENGINE env value

    @abstractmethod
    def synthesize(self, text: str, **options: Any) -> bytes:
        """Return raw WAV bytes for *text*."""
        ...

    def speak(self, text: str, **options: Any) -> TTSResponse:
        """Default: synthesise and wrap result in a response."""
        audio = self.synthesize(text, **options)
        return TTSResponse(
            ok=True,
            spoken=bool(audio),
            text=text,
            engine=self.engine_name,
        )
