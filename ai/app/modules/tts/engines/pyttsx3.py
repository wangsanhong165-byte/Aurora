"""pyttsx3 engine — system TTS fallback (no GPU needed)."""

from __future__ import annotations

import io
import os
import tempfile
from typing import Any

import numpy as np
import soundfile as sf

from app.core.schemas import TTSResponse
from app.modules.tts.base import BaseTTS
from app.modules.tts.factory import TTSFactory


# ---- module-level functions (backward compat) ---------------------------

def synthesize(text: str) -> bytes:
    """Return WAV bytes via pyttsx3 (saved to temp file)."""
    if not text.strip():
        return b""
    import pyttsx3

    eng = pyttsx3.init()
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    try:
        eng.save_to_file(text, tmp.name)
        eng.runAndWait()
        data, sr = sf.read(tmp.name, dtype="float32")
    finally:
        os.unlink(tmp.name)
    buf = io.BytesIO()
    sf.write(buf, data, sr, format="WAV")
    return buf.getvalue()


def speak(text: str) -> TTSResponse:
    """Synthesize and play locally via pyttsx3."""
    if not text.strip():
        return TTSResponse(ok=True, spoken=False, text=text, engine="pyttsx3")
    import pyttsx3

    eng = pyttsx3.init()
    eng.say(text)
    eng.runAndWait()
    return TTSResponse(ok=True, spoken=True, text=text, engine="pyttsx3")


# ---- class (factory-registered) -----------------------------------------

@TTSFactory.register
class Pyttsx3TTS(BaseTTS):
    engine_name = "pyttsx3"

    def __init__(self, config: Any = None, **kwargs: Any) -> None:
        super().__init__()

    def synthesize(self, text: str, **options: Any) -> bytes:
        return synthesize(text)

    def speak(self, text: str, **options: Any) -> TTSResponse:
        return speak(text)
