"""HTTPTTSProvider — implements TTSInterface via HTTP TTS service.

Wraps the existing HTTPTTSAdapter (from app.models.http_adapters) into
the canonical TTSInterface. Handles sync-to-async bridge via asyncio.to_thread.
"""

from __future__ import annotations

import asyncio

from app.interfaces.tts import TTSInterface
from app.models.http_adapters import HTTPTTSAdapter


class HTTPTTSProvider(TTSInterface):
    """Async wrapper around HTTPTTSAdapter for the CharacterTurn Runtime."""

    def __init__(self, base_url: str | None = None):
        self._adapter = HTTPTTSAdapter(base_url=base_url)

    async def synthesize(self, text: str, **kwargs) -> bytes:
        """Synthesize speech via the HTTP TTS service."""
        return await asyncio.to_thread(
            self._adapter.synthesize,
            text,
            **kwargs,
        )

    async def speak(self, text: str, voice: str = "", **kwargs) -> str:
        """Synthesize and mark as spoken (no separate playback step)."""
        await self.synthesize(text, voice=voice, **kwargs)
        return "spoken"
