"""Non‑blocking audio playback queue for voice agent."""

from __future__ import annotations

import queue
import threading
import time
from io import BytesIO
from typing import Optional

import numpy as np
import sounddevice as sd
import soundfile as sf


class AsyncAudioPlayer:
    """Background thread that plays queued WAV audio bytes non‑blocking."""

    def __init__(self, min_buffer: int = 2, buffer_timeout: float = 1.2) -> None:
        self._queue: queue.Queue = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._done_event = threading.Event()
        self._running = False
        self._is_playing = False
        self._min_buffer = min_buffer
        self._buffer_timeout = buffer_timeout
        self._first_play = True
        self._first_enqueue_time: Optional[float] = None
        self._buffered = False
        # Turn completion barrier: prevents premature idle during playback
        self._turn_active = False

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
        self._first_enqueue_time = None
        self._buffered = False
        self._turn_active = False
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
    # Turn barrier API
    # ------------------------------------------------------------------
    def begin_turn(self) -> None:
        """Signal start of a new response turn. Resets idle detection."""
        self._turn_active = True
        self._done_event.clear()
        self._buffered = False
        self._first_enqueue_time = None
        self._first_play = True

    def end_turn(self) -> None:
        """Signal that all sentences for this turn have been enqueued."""
        self._turn_active = False
        print(f"[PLAYER] turn_end t={time.time():.1f}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def enqueue(self, wav_bytes: bytes, text: Optional[str] = None) -> None:
        if not wav_bytes:
            return
        if self._first_enqueue_time is None:
            self._first_enqueue_time = time.time()
        self._queue.put((wav_bytes, text))

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
    _EMOTION_KW = {"理解", "抱歉", "辛苦", "慢慢", "别担心", "放心", "没关系", "相信",
                   "感谢", "谢谢", "不着急", "休息", "好吗", "好不好"}

    @staticmethod
    def _compute_pause(text):
        if not text:
            return 0.35
        length = len(text)
        if length < 8:
            pause = 0.15
            reason = "short"
        elif length <= 20:
            pause = 0.35
            reason = "normal"
        else:
            pause = 0.55
            reason = "long"
        if any(kw in text for kw in AsyncAudioPlayer._EMOTION_KW):
            pause += 0.20
            reason += "+emotion"
        if "?" in text or "吗" in text or "呢" in text or "如何" in text:
            pause += 0.15
            reason += "+question"
        pause = max(0.10, min(pause, 1.00))
        print(f"[PLAYER] pacing_pause={pause:.2f}s reason={reason}")
        return pause

    def _loop(self) -> None:
        while self._running:
            try:
                item = self._queue.get(timeout=0.1)
            except queue.Empty:
                # Only signal idle when: not playing AND turn has ended
                if not self._is_playing and not self._turn_active:
                    self._done_event.set()
                    pass  # idle (silent)
                continue

            if item is None:
                break

            wav_bytes, sentence_text = item if isinstance(item, tuple) else (item, None)

            if self._stop_event.is_set():
                self._queue.task_done()
                continue

            try:
                # Jitter buffer: wait for min_buffer items or timeout before first play
                if not self._buffered and self._first_enqueue_time is not None:
                    while self._queue.qsize() < self._min_buffer - 1:
                        elapsed = time.time() - self._first_enqueue_time
                        if elapsed > self._buffer_timeout:
                            break
                        time.sleep(0.05)
                    self._buffered = True

                data, sr = sf.read(BytesIO(wav_bytes), dtype="float32")
                if data.ndim == 1:
                    data = data.reshape(-1, 1)
                # Normalize: peak <= 0.95
                peak = float(abs(data).max())
                if peak > 0.95:
                    data = data * (0.95 / peak)
                # Silence padding before first play (prevents stream-init clipping)
                if self._first_play:
                    pad = np.zeros((int(0.1 * sr), 1), dtype="float32")
                    data = np.vstack([pad, data])
                    self._first_play = False

                qs = self._queue.qsize()
                print(f"[PLAYER] play_start t={time.time():.1f} queue_size={qs}")
                self._is_playing = True
                self._done_event.clear()
                sd.play(data, sr)
                # Wait for real stream completion — never exit on None
                was_active = False
                while True:
                    stream = sd.get_stream()
                    if stream is not None:
                        if stream.active:
                            was_active = True
                        elif was_active:
                            # Was playing, now stopped = finished
                            break
                    # stream is None: not yet initialized, keep waiting
                    if self._stop_event.is_set():
                        sd.stop()
                        break
                    time.sleep(0.05)
                print(f"[PLAYER] play_finish t={time.time():.1f} queue_size={self._queue.qsize()}")
                pause_s = self._compute_pause(sentence_text)
                if pause_s > 0:
                    time.sleep(pause_s)
            except Exception as exc:
                print(f"[Player] playback error: {exc}")
            finally:
                self._is_playing = False
                self._queue.task_done()

        self._is_playing = False
        self._done_event.set()