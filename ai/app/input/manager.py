"""Input state machine — continuous listening with VAD-based recording and continuation window."""

import time
from pathlib import Path

import numpy as np

from app.core.state import InputState
from app.input.recorder import AudioRecorder
from app.input.vad import VAD


class InputManager:
    """Manages the microphone pipeline with natural turn-taking.

    State flow:
        IDLE → LISTENING → RECORDING → CONTINUATION → (speech? back to RECORDING)
                                                      → (silence) PROCESSING → IDLE
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        silence_timeout: float = 1.5,
        continue_window: float = 1.0,
        min_utterance: float = 0.8,
        max_duration: float = 30.0,
        output_dir: Path | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_ms = 30
        self.frame_size = int(sample_rate * self.frame_ms / 1000)

        self.silence_timeout = silence_timeout
        self.continue_window = continue_window
        self.min_utterance = min_utterance
        self.max_duration = max_duration
        self.output_dir = output_dir or Path("recordings")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._state = InputState.IDLE
        self._vad = VAD(sample_rate, self.frame_ms)
        self._recorder = AudioRecorder(sample_rate, self.frame_size)

        # Pre-speech ring buffer
        self._pre_buffer: list[np.ndarray] = []
        self._pre_buffer_max = int(0.5 * 1000 / self.frame_ms)

        # Voice / silence tracking
        self._voiced_frames = 0
        self._silent_frames = 0
        self._trigger_count = int(0.5 * 1000 / self.frame_ms)
        self._silence_limit = int(silence_timeout * 1000 / self.frame_ms)
        self._max_frames = int(max_duration * 1000 / self.frame_ms)
        self._continue_limit = int(continue_window * 1000 / self.frame_ms)

        # Merged utterances for continuation
        self._all_audio: list[np.ndarray] = []
        self._started_at = 0.0
        self._stop_requested = False

    # ── public API ──────────────────────────────────────────────

    @property
    def state(self) -> InputState:
        return self._state

    def start(self) -> None:
        self._state = InputState.IDLE
        self._stop_requested = False
        self._all_audio.clear()
        print("[Input] State machine started (IDLE)")

    def stop(self) -> None:
        self._stop_requested = True
        if self._state in (InputState.LISTENING, InputState.RECORDING, InputState.CONTINUATION):
            self._recorder.stop()
        self._state = InputState.IDLE
        print("[Input] Stopped")

    def transition(self, new_state: InputState) -> None:
        self._state = new_state

    def poll(self) -> dict:
        """Return the next speech event. Blocks until available or stopped."""
        while not self._stop_requested:
            if self._state == InputState.IDLE:
                self._enter_idle()
            elif self._state == InputState.LISTENING:
                result = self._run_listening()
                if result:
                    return result
            elif self._state == InputState.CONTINUATION:
                result = self._run_continuation()
                if result:
                    return result
            elif self._state in (InputState.RECORDING, InputState.PROCESSING, InputState.SPEAKING):
                time.sleep(0.05)
        return {"type": "stop"}

    # ── IDLE → LISTENING ───────────────────────────────────────

    def _enter_idle(self) -> None:
        self._pre_buffer.clear()
        self._voiced_frames = 0
        self._silent_frames = 0
        self._all_audio.clear()
        self._state = InputState.LISTENING
        self._recorder.start()
        self._started_at = time.time()
        print("[Input] LISTENING...")

    # ── LISTENING → RECORDING ──────────────────────────────────

    def _run_listening(self) -> dict | None:
        if self._recorder._stream is None:
            self._recorder.start()

        import sounddevice as sd
        frame = sd.rec(self.frame_size, samplerate=self.sample_rate,
                       channels=1, dtype="float32", blocking=True)
        mono = frame.ravel()

        speech = self._vad.is_speech(mono)

        self._pre_buffer.append(mono.copy())
        if len(self._pre_buffer) > self._pre_buffer_max:
            self._pre_buffer.pop(0)

        if speech:
            self._voiced_frames += 1
        else:
            self._voiced_frames = max(0, self._voiced_frames - 1)

        if self._voiced_frames >= self._trigger_count:
            self._recorder.stop()
            self._state = InputState.RECORDING
            # Flush pre-buffer into recording buffer + accumulator
            pre = list(self._pre_buffer)
            self._recorder._buffer = pre
            self._all_audio.extend(pre)
            self._pre_buffer.clear()
            self._silent_frames = 0
            print("[Input] RECORDING...")
            return self._run_recording()

        if time.time() - self._started_at > 60:
            self._recorder.stop()
            self._state = InputState.IDLE
            return None
        return None

    # ── RECORDING → CONTINUATION ───────────────────────────────

    def _run_recording(self) -> dict | None:
        self._recorder.start()

        while not self._stop_requested:
            buf = self._recorder._buffer
            frame_count = len(buf)

            if frame_count > 0:
                check_window = min(10, frame_count)
                recent = np.concatenate(list(buf)[-check_window:])
                rms = float(np.sqrt(np.mean(recent ** 2)))
                if rms < 0.005:
                    self._silent_frames += check_window
                else:
                    self._silent_frames = 0

            if self._silent_frames >= self._silence_limit:
                break
            if frame_count >= self._max_frames:
                print(f"[Input] Max duration {self.max_duration:.0f}s reached")
                break
            time.sleep(0.05)

        audio = self._recorder.stop()
        if audio is not None:
            self._all_audio.append(audio)

        total_dur = sum(len(a) for a in self._all_audio) / self.sample_rate
        print(f"[Input] Segment done ({total_dur:.1f}s total), waiting for continuation...")

        # Enter continuation window
        self._state = InputState.CONTINUATION
        self._silent_frames = 0
        self._voiced_frames = 0
        self._pre_buffer.clear()
        self._recorder.start()
        self._continue_start = time.time()
        print(f"[Input] CONTINUATION ({self.continue_window:.1f}s window)...")
        return None  # will be handled in next poll()

    # ── CONTINUATION → speech event or back to RECORDING ───────

    def _run_continuation(self) -> dict | None:
        import sounddevice as sd
        frame = sd.rec(self.frame_size, samplerate=self.sample_rate,
                       channels=1, dtype="float32", blocking=True)
        mono = frame.ravel()

        speech = self._vad.is_speech(mono)

        if speech:
            self._voiced_frames += 1
            self._silent_frames = 0
        else:
            self._voiced_frames = max(0, self._voiced_frames - 1)
            self._silent_frames += 1

        # User continued speaking → go back to RECORDING
        if self._voiced_frames >= self._trigger_count:
            print("[Input] User continued — extending recording")
            audio = self._recorder.stop()
            if audio is not None:
                self._all_audio.append(audio)
            self._state = InputState.RECORDING
            self._recorder._buffer = []
            self._silent_frames = 0
            return self._run_recording()

        # Continuation window expired → finalize utterance
        if self._silent_frames >= self._continue_limit or \
           time.time() - self._continue_start > self.continue_window + 0.5:
            self._recorder.stop()
            return self._finalize_utterance()

        return None

    def _finalize_utterance(self) -> dict:
        total = np.concatenate(self._all_audio) if self._all_audio else np.zeros(0)
        duration = len(total) / self.sample_rate

        if duration < self.min_utterance:
            print(f"[Input] Too short ({duration:.1f}s < {self.min_utterance:.1f}s), ignoring")
            self._state = InputState.IDLE
            return {"type": "empty"}

        path = self.output_dir / "latest.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        import soundfile as sf
        sf.write(str(path), total, self.sample_rate)
        print(f"[Input] Utterance ready: {duration:.1f}s → {path}")

        self._state = InputState.PROCESSING
        return {"type": "speech", "audio_path": str(path), "duration": duration}
