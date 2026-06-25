"""Edge TTS engine — free Microsoft neural voices, no GPU needed."""
import asyncio
import io
import os
from typing import Any

import numpy as np
import soundfile as sf

from app.modules.tts.base import BaseTTS
from app.modules.tts.factory import TTSFactory


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



@TTSFactory.register
class EdgeTTS(BaseTTS):
    engine_name = "edge-tts"

    def __init__(self, config: Any = None, **kwargs: Any) -> None:
        super().__init__()
        self._voice = os.environ.get("TTS_EDGE_VOICE", "zh-CN-XiaoxiaoNeural")
        if config is not None:
            from app.config_manager import EdgeTTSConfig
            if isinstance(config, EdgeTTSConfig) and config.voice:
                self._voice = config.voice

    def synthesize(self, text: str, **options: Any) -> bytes:
        text = text.strip()
        if not text:
            return b""
        return asyncio.run(_synthesize_edge(text, self._voice))
