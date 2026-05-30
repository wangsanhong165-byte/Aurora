"""Voice Activity Detection using webrtcvad — extracted from recorder API."""

import numpy as np
import webrtcvad


class VAD:
    """Thin wrapper around webrtcvad with frame buffering."""

    def __init__(self, sample_rate: int = 16000, frame_ms: int = 30, aggressiveness: int = 2) -> None:
        if frame_ms not in (10, 20, 30):
            raise ValueError("frame_ms must be 10, 20, or 30")
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.frame_size = int(sample_rate * frame_ms / 1000)
        self._vad = webrtcvad.Vad(aggressiveness)

    def is_speech(self, audio: np.ndarray) -> bool:
        """audio: 1D float32 array [-1, 1] of frame_size samples."""
        if len(audio) != self.frame_size:
            return False
        pcm = (audio * 32767).astype(np.int16).tobytes()
        return self._vad.is_speech(pcm, self.sample_rate)

    def is_speech_raw(self, pcm: bytes) -> bool:
        return self._vad.is_speech(pcm, self.sample_rate)
