"""Edge TTS engine — free Microsoft neural voices, no GPU needed."""
import asyncio
import io
import os
import tempfile
from pathlib import Path

import soundfile as sf
import numpy as np


async def _synthesize_edge(text: str, voice: str) -> bytes:
    """Stream Edge TTS audio chunks into WAV bytes."""
    from edge_tts import Communicate

    out = io.BytesIO()
    tts = Communicate(text, voice)
    async for chunk in tts.stream():
        if chunk["type"] == "audio":
            out.write(chunk["data"])
    out.seek(0)

    # Edge TTS outputs MP3, convert to WAV for player compatibility
    data, sr = sf.read(out, dtype="float32")
    if data.ndim == 1:
        data = data.reshape(-1, 1)

    wav = io.BytesIO()
    sf.write(wav, data, sr, format="WAV")
    return wav.getvalue()


def synthesize(text: str) -> bytes:
    """Sync wrapper — called by TTS router."""
    voice = os.environ.get("TTS_EDGE_VOICE", "zh-CN-XiaoxiaoNeural")
    text = text.strip()
    if not text:
        return b""
    return asyncio.run(_synthesize_edge(text, voice))
