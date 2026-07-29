"""HTTPASRProvider — implements ASRInterface via HTTP ASR service.

Wraps the existing HTTPASRAdapter (from app.models.http_adapters) into
the canonical ASRInterface. Handles sync-to-async bridge via asyncio.to_thread.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import soundfile as sf

from app.interfaces.asr import ASRInterface
from app.models.http_adapters import HTTPASRAdapter


class HTTPASRProvider(ASRInterface):
    """Async wrapper around HTTPASRAdapter for the CharacterTurn Runtime.

    Bridges the gap between ASRInterface (takes audio bytes) and
    HTTPASRAdapter (takes a file path) by writing audio to a temp file.
    """

    def __init__(self, base_url: str | None = None):
        self._adapter = HTTPASRAdapter(base_url=base_url)

    async def transcribe(self, audio: bytes, language: str | None = None) -> str:
        """Transcribe audio bytes via the HTTP ASR service."""
        # Write audio bytes to a temp file (the HTTP adapter needs a path)
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp.name
        try:
            tmp.write(audio)
            tmp.close()

            result = await asyncio.to_thread(
                self._adapter.transcribe,
                tmp_path,
                language=language,
            )
            return result.get("text", "")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
