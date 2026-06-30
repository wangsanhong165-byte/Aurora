"""Interrupt detection — detects barge-in attempts during TTS playback."""

import queue

import numpy as np


class InterruptDetector:
    """Monitors audio frames for speech during TTS playback.

    Since TTS blocks the main thread, we check the accumulated
    frame queue after playback finishes. If speech was detected
    during playback, the agent can skip the idle pause and
    respond immediately.
    """

    def __init__(self, rms_threshold: float = 0.01) -> None:
        self.rms_threshold = rms_threshold
        self._interrupted = False
        self._speech_frames: list[np.ndarray] = []

    def reset(self) -> None:
        self._interrupted = False
        self._speech_frames.clear()

    def feed(self, frame: np.ndarray) -> None:
        """Feed a frame during monitoring. Called from the audio callback."""
        self._speech_frames.append(frame.copy())
        rms = float(np.sqrt(np.mean(frame ** 2)))
        if rms > self.rms_threshold:
            self._interrupted = True

    @property
    def interrupted(self) -> bool:
        return self._interrupted

    def drain(self) -> list[np.ndarray]:
        """Get accumulated frames and reset."""
        frames = list(self._speech_frames)
        self.reset()
        return frames
