"""Input state machine — continuous listening with VAD-based recording."""

import time
from pathlib import Path

import numpy as np

from app.core.state import InputState
from app.input.recorder import AudioRecorder
from app.input.vad import VAD


class InputManager:
    """Manages the microphone pipeline: IDLE → LISTENING → RECORDING → PROCESSING → SPEAKING.

    Usage:
        mgr = InputManager()
        mgr.start()

        while True:
            event = mgr.poll()
            if event["type"] == "speech":
                process(event["audio_path"])
                mgr.transition(InputState.PROCESSING)
                # ... ASR / LLM / TTS ...
                mgr.transition(InputState.IDLE)
    """

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
        self._recorder = AudioRecorder(sample_rate, self.frame_size)

        # Pre-speech ring buffer (0.5s)
        self._pre_buffer: list[np.ndarray] = []
        self._pre_buffer_max = int(0.5 * 1000 / self.frame_ms)  # frames

        # Trigger / silence counters
        self._voiced_frames = 0
        self._silent_frames = 0
        self._trigger_count = int(0.5 * 1000 / self.frame_ms)   # ~7 frames
        self._silence_limit = int(silence_timeout * 1000 / self.frame_ms)
        self._max_frames = int(max_duration * 1000 / self.frame_ms)

        self._started_at = 0.0
        self._stop_requested = False

    # ── public API ──────────────────────────────────────────────

    @property
    def state(self) -> InputState:
        return self._state

    def start(self) -> None:
        self._state = InputState.IDLE
        self._stop_requested = False
        print("[Input] State machine started (IDLE)")

    def stop(self) -> None:
        self._stop_requested = True
        if self._state in (InputState.LISTENING, InputState.RECORDING):
            self._recorder.stop()
        self._state = InputState.IDLE
        print("[Input] Stopped")

    def transition(self, new_state: InputState) -> None:
        self._state = new_state

    def poll(self) -> dict:
        """Return the next event. Blocks until an event is available."""
        while not self._stop_requested:
            if self._state == InputState.IDLE:
                self._enter_idle()
            elif self._state == InputState.LISTENING:
                result = self._run_listening()
                if result:
                    return result
            elif self._state in (InputState.RECORDING, InputState.PROCESSING, InputState.SPEAKING):
                time.sleep(0.05)
        return {"type": "stop"}

    # ── internal ────────────────────────────────────────────────

    def _enter_idle(self) -> None:
        self._pre_buffer.clear()
        self._voiced_frames = 0
        self._silent_frames = 0
        self._state = InputState.LISTENING
        self._recorder.start()  # stream for pre-buffer
        self._started_at = time.time()
        print("[Input] LISTENING...")

    def _run_listening(self) -> dict | None:
        """Stream one frame through VAD. Return speech event when triggered."""
        if self._recorder._stream is None:
            self._recorder.start()

        # Read one frame via the stream
        # InputStream with callback fills _buffer automatically;
        # we poll with a short sleep, then examine the latest frame.
        # Simpler: use a blocking read approach instead of callback.

        # Actually, we need to redesign: InputStream callback is async.
        # Use sd.rec() for frame-by-frame reads instead.
        import sounddevice as sd
        import numpy as np

        frame = sd.rec(
            self.frame_size,
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocking=True,
        )
        mono = frame.ravel()

        # VAD check
        speech = self._vad.is_speech(mono)

        # Pre-buffer
        self._pre_buffer.append(mono.copy())
        if len(self._pre_buffer) > self._pre_buffer_max:
            self._pre_buffer.pop(0)

        if speech:
            self._voiced_frames += 1
        else:
            self._voiced_frames = max(0, self._voiced_frames - 1)

        if self._voiced_frames >= self._trigger_count:
            # Triggered! Start recording.
            self._recorder.stop()
            self._state = InputState.RECORDING
            self._recorder._buffer = list(self._pre_buffer)  # flush pre-buffer
            self._pre_buffer.clear()
            self._silent_frames = 0
            print("[Input] RECORDING...")
            return self._run_recording()

        # Safety timeout: if no speech for too long, restart
        if time.time() - self._started_at > 60:
            self._recorder.stop()
            self._state = InputState.IDLE
            print("[Input] Listening timeout, restarting IDLE")
            return None

        return None

    def _run_recording(self) -> dict:
        """Record until silence. Called after VAD trigger."""
        self._recorder.start()

        while not self._stop_requested:
            # Check if we have new frames in buffer
            frame_count = len(self._recorder._buffer)

            # Approximate silence detection
            if frame_count > 0:
                # Check last N frames for silence
                check_window = min(10, frame_count)
                recent = np.concatenate(list(self._recorder._buffer)[-check_window:])
                rms = float(np.sqrt(np.mean(recent ** 2)))
                if rms < 0.005:  # silent
                    self._silent_frames += check_window
                else:
                    self._silent_frames = 0

            if self._silent_frames >= self._silence_limit:
                break
            if frame_count >= self._max_frames:
                print(f"[Input] Max duration {self.max_duration:.0f}s reached")
                break

            import time
            time.sleep(0.05)

        audio = self._recorder.stop()
        if audio is None:
            return {"type": "empty"}

        path = self.output_dir / "latest.wav"
        self._recorder.save(path, audio)
        duration = len(audio) / self.sample_rate
        print(f"[Input] Recorded {duration:.1f}s → {path}")

        if duration < 0.5:
            print(f"[Input] Too short ({duration:.1f}s), ignoring")
            self._state = InputState.IDLE
            return {"type": "empty"}

        self._state = InputState.PROCESSING
        return {"type": "speech", "audio_path": str(path), "duration": duration}

