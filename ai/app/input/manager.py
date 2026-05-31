"""Input state machine — continuous listening with VAD-based recording."""

import queue
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from app.core.state import InputState
from app.input.vad import VAD


class InputManager:
    """Manages the microphone pipeline: IDLE → LISTENING → RECORDING → PROCESSING → SPEAKING."""

    def __init__(
        self,
        sample_rate: int = 16000,
        silence_timeout: float = 1.5,
        max_duration: float = 30.0,
        output_dir: Path | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_ms = 30
        self.frame_size = int(sample_rate * self.frame_ms / 1000)

        self.silence_timeout = silence_timeout
        self.max_duration = max_duration
        self.output_dir = output_dir or Path("recordings")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._state = InputState.IDLE
        self._vad = VAD(sample_rate, self.frame_ms)
        self._stop_requested = False

        # Single stream + frame queue for entire lifecycle
        self._frame_queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: sd.InputStream | None = None

        # Pre-speech ring buffer
        self._pre_buffer: list[np.ndarray] = []
        self._pre_buffer_max = int(0.5 * 1000 / self.frame_ms)

        # Recording buffer
        self._record_buffer: list[np.ndarray] = []

        # Counters
        self._voiced_frames = 0
        self._silent_frames = 0
        self._trigger_count = int(0.2 * 1000 / self.frame_ms)
        self._silence_limit = int(silence_timeout * 1000 / self.frame_ms)
        self._max_frames = int(max_duration * 1000 / self.frame_ms)
        self._min_record_frames = int(1.0 * 1000 / self.frame_ms)  # at least 1s before silence can stop

    @property
    def state(self) -> InputState:
        return self._state

    def start(self) -> None:
        self._state = InputState.IDLE
        self._stop_requested = False
        self._open_stream()
        print("[Input] State machine started")

    def stop(self) -> None:
        self._stop_requested = True
        self._close_stream()
        self._state = InputState.IDLE
        print("[Input] Stopped")

    def transition(self, new_state: InputState) -> None:
        self._state = new_state

    def poll(self) -> dict:
        """Return the next event. Blocks until speech detected or stop requested."""
        self._enter_idle()

        while not self._stop_requested:
            if self._state == InputState.LISTENING:
                result = self._run_listening()
                if result:
                    return result
            elif self._state == InputState.RECORDING:
                return self._run_recording()
            elif self._state in (InputState.PROCESSING, InputState.SPEAKING):
                time.sleep(0.05)
        return {"type": "stop"}

    # ── stream ──────────────────────────────────────────────────

    def _open_stream(self) -> None:
        self._close_stream()

        def _callback(indata: np.ndarray, _frames: int, _time, _status) -> None:
            mono = indata if indata.ndim == 1 else indata[:, 0]
            try:
                self._frame_queue.put_nowait(mono.copy())
            except queue.Full:
                pass

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.frame_size,
            callback=_callback,
        )
        self._stream.start()

    def _close_stream(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        # Drain queue
        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                break

    def _read_frame(self, timeout: float = 0.5) -> np.ndarray | None:
        try:
            return self._frame_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _drain_queue(self) -> None:
        """Flush all pending frames from the queue."""
        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                break

    # ── state transitions ───────────────────────────────────────

    def _enter_idle(self) -> None:
        self._pre_buffer.clear()
        self._record_buffer.clear()
        self._voiced_frames = 0
        self._silent_frames = 0
        self._state = InputState.LISTENING
        # Drain stale frames accumulated during PROCESSING/SPEAKING
        self._drain_queue()
        print("[Input] LISTENING...")

    def _run_listening(self) -> dict | None:
        """Read frames from queue, check VAD. Trigger when enough speech."""
        mono = self._read_frame(timeout=0.1)
        if mono is None:
            return None

        speech = self._vad.is_speech(mono)

        self._pre_buffer.append(mono)
        if len(self._pre_buffer) > self._pre_buffer_max:
            self._pre_buffer.pop(0)

        if speech:
            self._voiced_frames += 1
        else:
            self._voiced_frames = max(0, self._voiced_frames - 1)

        if self._voiced_frames >= self._trigger_count:
            self._state = InputState.RECORDING
            self._record_buffer = list(self._pre_buffer)
            self._pre_buffer.clear()
            print("[Input] RECORDING...")
            return None

        return None

    def _run_recording(self) -> dict:
        """Accumulate frames until silence or max duration."""
        self._silent_frames = 0
        started = time.time()

        while not self._stop_requested:
            mono = self._read_frame(timeout=0.1)
            if mono is None:
                continue

            self._record_buffer.append(mono)

            # RMS-based silence detection
            rms = float(np.sqrt(np.mean(mono ** 2)))
            if rms < 0.005:
                self._silent_frames += 1
            else:
                self._silent_frames = 0

            if self._silent_frames >= self._silence_limit and len(self._record_buffer) >= self._min_record_frames:
                break
            if len(self._record_buffer) >= self._max_frames:
                print(f"[Input] Max duration {self.max_duration:.0f}s reached")
                break
            if time.time() - started > self.max_duration + 5:
                break

        if not self._record_buffer:
            return {"type": "empty"}

        audio = np.concatenate(self._record_buffer)
        path = self.output_dir / "latest.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(path), audio, self.sample_rate)
        duration = len(audio) / self.sample_rate
        print(f"[Input] Recorded {duration:.1f}s → {path}")

        self._state = InputState.PROCESSING
        return {"type": "speech", "audio_path": str(path), "duration": duration}
