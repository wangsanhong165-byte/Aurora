"""Thread-safe ring buffer for 16kHz mono float32 audio."""

from __future__ import annotations

import threading
from collections import deque

import numpy as np


class AudioRingBuffer:
    """Lock-protected ring buffer for accumulating audio samples.

    Recording thread writes via ``write()``; inference thread reads
    via ``read_last()`` / ``read_all()``.  All methods are thread-safe.
    """

    def __init__(self, max_duration: float = 30.0, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate
        maxlen = int(max_duration * sample_rate)
        self._buf: deque[float] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._total_written = 0

    # ------------------------------------------------------------------
    def write(self, chunk: np.ndarray) -> None:
        """Append a chunk of float32 samples (1-D)."""
        with self._lock:
            self._buf.extend(chunk.ravel().tolist())
            self._total_written += len(chunk)

    # ------------------------------------------------------------------
    def read_all(self) -> np.ndarray:
        """Return a copy of all buffered samples as float32 numpy array."""
        with self._lock:
            return np.array(list(self._buf), dtype=np.float32)

    def read_last(self, duration: float) -> np.ndarray:
        """Return the most recent *duration* seconds of audio."""
        n = int(duration * self.sample_rate)
        with self._lock:
            items = list(self._buf)
            start = max(0, len(items) - n)
            return np.array(items[start:], dtype=np.float32)

    def read_range(self, start_sample: int, end_sample: int) -> np.ndarray:
        """Return audio between sample indices [start, end)."""
        with self._lock:
            items = list(self._buf)
            a = max(0, min(start_sample, len(items)))
            b = max(a, min(end_sample, len(items)))
            return np.array(items[a:b], dtype=np.float32)

    # ------------------------------------------------------------------
    def clear(self) -> None:
        with self._lock:
            self._buf.clear()

    @property
    def duration(self) -> float:
        with self._lock:
            return len(self._buf) / self.sample_rate

    @property
    def total_samples(self) -> int:
        with self._lock:
            return len(self._buf)

    @property
    def total_written(self) -> int:
        return self._total_written
