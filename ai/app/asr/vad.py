"""Silero VAD wrapper for speech / silence detection.

Supports both the ``silero-vad`` PyPI package and the torch.hub fallback.
If neither is available, falls back to a simple energy-based detector
so the module is always importable.
"""

from __future__ import annotations

import enum
import time
from typing import Optional

import numpy as np


class VADState(enum.Enum):
    SILENCE = "silence"
    SPEECH = "speech"


class VADProcessor:
    """Per-frame VAD with sentence-boundary detection.

    Parameters
    ----------
    sample_rate:
        Audio sample rate (must be 8000 or 16000 for Silero).
    silence_timeout:
        Seconds of continuous silence that mark a sentence end.
    speech_start_frames:
        Number of consecutive speech frames required to transition
        from SILENCE → SPEECH (prevents noise false-positives).
    frame_duration:
        Duration of one VAD frame in seconds.  Silero natively uses
        30 ms for 8 kHz / 60 ms for 16 kHz — this value is
        informational; frames are fed externally.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        silence_timeout: float = 0.8,
        speech_start_frames: int = 3,
        frame_duration: float = 0.032,  # 512 samples @ 16kHz
    ) -> None:
        self.sample_rate = sample_rate
        self.silence_timeout = silence_timeout
        self.speech_start_frames = speech_start_frames
        self.frame_duration = frame_duration

        self._model: Optional[object] = None
        self._get_speech_prob = self._init_model()

        self._state: VADState = VADState.SILENCE
        self._speech_started_at: Optional[float] = None
        self._silence_started_at: float = time.monotonic()
        self._consecutive_speech = 0
        self._consecutive_silence = 0
        self._frame_count = 0

        # Ring buffer of recent speech probs for smoothing
        self._prob_history: list[float] = []

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------
    def _init_model(self):
        """Try Silero VAD; fall back to energy-based."""
        # 1. silero-vad PyPI package
        try:
            from silero_vad import load_silero_vad
            model = load_silero_vad(onnx=True)
            def _onnx_prob(audio: np.ndarray) -> float:
                return model(audio, self.sample_rate).item()
            self._model = model
            return _onnx_prob
        except ImportError:
            pass

        # 2. torch.hub
        try:
            import torch
            model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                onnx=False,
            )
            self._model = model
            def _torch_prob(audio: np.ndarray) -> float:
                t = torch.from_numpy(audio).float()
                return model(t, self.sample_rate).item()
            return _torch_prob
        except Exception:
            pass

        # 3. Energy-based fallback
        return self._energy_vad

    @staticmethod
    def _energy_vad(audio: np.ndarray, threshold: float = 0.005) -> float:
        """Simple RMS-energy detector. Returns 0.0 or 1.0."""
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
        return 1.0 if rms > threshold else 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def process(self, frame: np.ndarray) -> VADState:
        """Feed one audio frame and return current VAD state.

        Parameters
        ----------
        frame:
            1-D float32 array.  Typical size: ``sample_rate * frame_duration``
            samples (e.g. 480 for 16 kHz @ 30 ms).

        Returns
        -------
        VADState
        """
        prob = self._get_speech_prob(frame)
        self._prob_history.append(prob)
        if len(self._prob_history) > 10:
            self._prob_history.pop(0)

        is_speech = prob > 0.5
        now = time.monotonic()
        self._frame_count += 1

        if is_speech:
            self._consecutive_speech += 1
            self._consecutive_silence = 0
            if self._state == VADState.SILENCE and self._consecutive_speech >= self.speech_start_frames:
                self._state = VADState.SPEECH
                self._speech_started_at = now
        else:
            self._consecutive_silence += 1
            self._consecutive_speech = 0
            if self._state == VADState.SPEECH:
                silence_dur = self._consecutive_silence * self.frame_duration
                if silence_dur >= self.silence_timeout:
                    self._state = VADState.SILENCE
                    self._silence_started_at = now
                    self._consecutive_silence = 0  # reset for just_stopped_speaking

        return self._state

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------
    @property
    def state(self) -> VADState:
        return self._state

    @property
    def is_speech(self) -> bool:
        return self._state == VADState.SPEECH

    @property
    def is_silence(self) -> bool:
        return self._state == VADState.SILENCE

    def just_started_speaking(self) -> bool:
        """True on the exact frame where speech begins."""
        return self._state == VADState.SPEECH and self._consecutive_speech == self.speech_start_frames

    def just_stopped_speaking(self) -> bool:
        """True on the exact frame where the silence timeout triggers."""
        if self._state != VADState.SILENCE:
            return False
        # Check if we just transitioned (consecutive silence == 1 after reset)
        return self._consecutive_silence == 1 and self._frame_count > 1

    def speech_duration(self) -> float:
        """How long the current speech segment has lasted (seconds)."""
        if self._speech_started_at is None:
            return 0.0
        return time.monotonic() - self._speech_started_at

    def reset(self) -> None:
        """Reset internal state for a fresh utterance."""
        self._state = VADState.SILENCE
        self._speech_started_at = None
        self._silence_started_at = time.monotonic()
        self._consecutive_speech = 0
        self._consecutive_silence = 0
        self._frame_count = 0
        self._prob_history.clear()

    @property
    def speech_prob(self) -> float:
        """Smoothed speech probability (0-1)."""
        if not self._prob_history:
            return 0.0
        return float(np.mean(self._prob_history[-5:]))
