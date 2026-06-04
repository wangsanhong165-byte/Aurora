"""pyttsx3 engine — system TTS fallback, no GPU needed."""
from __future__ import annotations


def synthesize(text: str) -> bytes:
    """pyttsx3 only supports playback, not bytes output. Returns empty.
       For the synthesize endpoint, this engine is NOT suitable.
       Use the /v1/tts/speak endpoint instead."""
    raise RuntimeError("pyttsx3 does not support synthesize (bytes output). Use /v1/tts/speak.")
