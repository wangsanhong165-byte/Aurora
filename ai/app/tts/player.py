"""Non‑blocking audio playback queue for voice agent."""

from __future__ import annotations

import queue
import threading
import time
from io import BytesIO
from typing import Optional

import sounddevice as sd
import soundfile as sf


class AsyncAudioPlayer:
    """Background thread that plays queued WAV audio bytes non‑blocking."""

    def __init__(self) -> None:
        self._queue: queue.Queue[Optional[bytes]] = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._done_event = threading.Event()
        self._running = False
        self._is_playing = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._done_event.clear()
        self._is_playing = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def shutdown(self, wait: bool = False) -> None:
        if not self._running:
            return
        if wait:
            self._queue.put(None)
            self._thread.join(timeout=5.0)
        else:
            self._stop_event.set()
            self._queue.put(None)
        self._running = False
        self._thread = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def enqueue(self, wav_bytes: bytes) -> None:
        if not wav_bytes:
            return
        self._queue.put(wav_bytes)

    def stop(self) -> None:
        """Stop current playback and flush the queue (for interrupt)."""
        self._stop_event.set()
        while True:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break

    def resume(self) -> None:
        """Clear stop flag so new audio can play after a stop()."""
        self._stop_event.clear()

    def clear(self) -> None:
        self.stop()

    def wait_done(self, timeout: Optional[float] = None) -> bool:
        if not self._running:
            return True
        return self._done_event.wait(timeout=timeout)

    @property
    def is_playing(self) -> bool:
        return self._is_playing or self._queue.qsize() > 0

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _loop(self) -> None:
        while self._running:
            try:
                wav_bytes = self._queue.get(timeout=0.1)
            except queue.Empty:
                if not self._is_playing:
                    self._done_event.set()
                continue

            if wav_bytes is None:
                break

            if self._stop_event.is_set():
                self._queue.task_done()
                continue

            try:
                data, sr = sf.read(BytesIO(wav_bytes), dtype="float32")
                if data.ndim == 1:
                    data = data.reshape(-1, 1)
                self._is_playing = True
                self._done_event.clear()
                sd.play(data, sr)
                duration = len(data) / sr
                step = 0.05
                elapsed = 0.0
                while elapsed < duration + 0.5:
                    if self._stop_event.is_set():
                        sd.stop()
                        break
                    time.sleep(step)
                    elapsed += step
            except Exception as exc:
                print(f"[Player] playback error: {exc}")
            finally:
                self._is_playing = False
                self._queue.task_done()

        self._is_playing = False
        self._done_event.set()
