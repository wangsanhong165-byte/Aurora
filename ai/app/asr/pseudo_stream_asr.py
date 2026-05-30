"""Pseudo-streaming ASR — incremental transcription with chunk + overlap.

Orchestrates audio capture (sounddevice), VAD, periodic ASR inference
on a sliding window, and LCP‑based text deduplication to deliver a
near‑realtime transcription experience without relying on true
streaming model APIs.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Awaitable, Callable, Optional, Union

import numpy as np
import sounddevice as sd
import soundfile as sf

from app.asr.audio_buffer import AudioRingBuffer
from app.asr.diff import TextDeduper
from app.asr.vad import VADProcessor, VADState

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
PartialCallback = Callable[[str], Union[None, Awaitable[None]]]
FinalCallback = Callable[[str], Union[None, Awaitable[None]]]
ASRTranscriber = Callable[[str], str]  # audio_path → text


# ---------------------------------------------------------------------------
# Default: Qwen3-ASR via HuggingFace
# ---------------------------------------------------------------------------
def _default_transcriber_factory(model_dir: Optional[str] = None):
    """Return a callable ``(audio_path) -> text`` using Qwen3ASRModel."""
    from app.core.config import DEFAULT_MODEL_DIR

    resolved_dir = Path(model_dir) if model_dir else DEFAULT_MODEL_DIR

    import torch
    from qwen_asr import Qwen3ASRModel

    device_map = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32

    model = Qwen3ASRModel.from_pretrained(
        str(resolved_dir),
        dtype=dtype,
        device_map=device_map,
        max_inference_batch_size=1,
        max_new_tokens=256,
    )

    def transcribe(audio_path: str, language: Optional[str] = None) -> str:
        results = model.transcribe(audio=str(audio_path), language=language)
        return results[0].text.strip() if results else ""

    return transcribe


# ---------------------------------------------------------------------------
# PseudoStreamASR
# ---------------------------------------------------------------------------
class PseudoStreamASR:
    """Incremental speech recognition with pseudo-streaming.

    Parameters
    ----------
    transcribe:
        Callable ``(audio_path) -> text``.  Defaults to a local
        Qwen3-ASR-1.7B instance loaded via HuggingFace.
    sample_rate:
        Audio sample rate.  Must match the model (16 000 for Qwen3).
    chunk_duration:
        How often (seconds) to trigger an incremental ASR inference
        during active speech.
    window_duration:
        Sliding window size (seconds) for partial ASR.  The model sees
        the most recent ``window_duration`` seconds of audio.
    silence_timeout:
        Seconds of continuous silence after which the current utterance
        is considered finished.
    speech_start_frames:
        Consecutive VAD speech frames required to begin a new utterance.
    max_utterance:
        Hard cap on utterance duration (seconds).  Forces finalisation.
    model_dir:
        Path to Qwen3-ASR model (used only when *transcribe* is None).
    language:
        Optional language hint passed to the ASR model.
    on_partial:
        Async/sync callback receiving incremental text suffix.
    on_final:
        Async/sync callback receiving final complete utterance text.

    Example
    -------
    >>> asr = PseudoStreamASR(
    ...     on_partial=lambda text: print(f"→ {text}", end="", flush=True),
    ...     on_final=lambda text: print(f"\\n[FINAL] {text}"),
    ... )
    >>> asyncio.run(asr.run())
    """

    def __init__(
        self,
        transcribe: Optional[ASRTranscriber] = None,
        sample_rate: int = 16000,
        chunk_duration: float = 0.5,
        window_duration: float = 2.0,
        silence_timeout: float = 0.8,
        speech_start_frames: int = 3,
        max_utterance: float = 30.0,
        model_dir: Optional[str] = None,
        language: Optional[str] = None,
        on_partial: Optional[PartialCallback] = None,
        on_final: Optional[FinalCallback] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.chunk_duration = chunk_duration
        self.window_duration = window_duration
        self.silence_timeout = silence_timeout
        self.max_utterance = max_utterance
        self.language = language

        self._on_partial = on_partial
        self._on_final = on_final

        # Audio buffer
        self._buffer = AudioRingBuffer(max_duration=60.0, sample_rate=sample_rate)

        # VAD frame size: 30 ms @ 16 kHz = 480 samples
        self._vad_frame_size = int(0.03 * sample_rate)
        self._vad = VADProcessor(
            sample_rate=sample_rate,
            silence_timeout=silence_timeout,
            speech_start_frames=speech_start_frames,
            frame_duration=0.03,
        )

        # ASR
        self._transcribe = transcribe or _default_transcriber_factory(model_dir)
        self._executor = ThreadPoolExecutor(max_workers=1)

        # State tracking
        self._deduper = TextDeduper()
        self._speech_start_sample: int = 0
        self._last_asr_time: float = 0.0
        self._running = False
        self._stream: Optional[sd.InputStream] = None
        self._vad_offset: int = 0  # sample offset for VAD processing

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def run(self) -> None:
        """Start recording and pseudo-streaming loop.  Blocks until stopped."""
        self._running = True
        self._start_recording()

        try:
            await self._main_loop()
        finally:
            self._stop_recording()
            self._executor.shutdown(wait=False)

    def stop(self) -> None:
        """Signal the loop to stop (e.g. from a signal handler)."""
        self._running = False


    # Recording
    # ------------------------------------------------------------------
    def _audio_callback(self, indata: np.ndarray, frames: int,
                        _time_info, status: int) -> None:
        """sounddevice callback — runs in PortAudio thread."""
        if status:
            print(f"[audio] warning: {status}")
        self._buffer.write(indata.copy().ravel())

    def _start_recording(self) -> None:
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self._vad_frame_size,
            callback=self._audio_callback,
        )
        self._stream.start()

    def _stop_recording(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    # ------------------------------------------------------------------
    # Main async loop
    # ------------------------------------------------------------------
    async def _main_loop(self) -> None:
        """Poll VAD, trigger ASR, handle state transitions."""
        utterance_count = 0
        last_vad_check = time.monotonic()

        while self._running:
            await asyncio.sleep(0.03)  # ~30 ms, matching VAD frame rate

            if self._buffer.total_samples <= self._vad_offset:
                continue

            # --- VAD: process new frames ---
            while self._vad_offset + self._vad_frame_size <= self._buffer.total_samples:
                frame = self._buffer.read_range(
                    self._vad_offset, self._vad_offset + self._vad_frame_size
                )
                self._vad_offset += self._vad_frame_size
                prev_state = self._vad.state
                self._vad.process(frame)

                # Speech just started
                if prev_state == VADState.SILENCE and self._vad.state == VADState.SPEECH:
                    self._speech_start_sample = self._buffer.total_written
                    self._last_asr_time = time.monotonic()
                    self._deduper.reset()
                    utterance_count += 1

                # Sentence end (silence timeout triggered)
                if self._vad.just_stopped_speaking():
                    await self._finalize_utterance()
                    self._deduper.reset()
                    self._vad.reset()

            # --- ASR trigger during speech ---
            now = time.monotonic()
            if self._vad.is_speech:
                speech_dur = now - self._last_asr_time
                if speech_dur >= self.chunk_duration:
                    await self._run_partial_asr()
                    self._last_asr_time = now

                # Hard cap
                utterance_dur = self._vad.speech_duration()
                if utterance_dur >= self.max_utterance:
                    await self._finalize_utterance()
                    self._deduper.reset()
                    self._vad.reset()

    # ------------------------------------------------------------------
    # ASR helpers
    # ------------------------------------------------------------------
    async def _run_partial_asr(self) -> None:
        """Run ASR on the sliding window and emit partial text suffix."""
        window_samples = int(self.window_duration * self.sample_rate)
        total = self._buffer.total_samples
        start_sample = max(0, total - window_samples)

        audio = self._buffer.read_range(start_sample, total)
        if len(audio) < self.sample_rate * 0.2:  # at least 200 ms
            return

        text = await self._transcribe_async(audio)
        if not text:
            return

        full, suffix = self._deduper.update(text)
        if suffix and self._on_partial:
            await self._emit(self._on_partial, suffix)

    async def _finalize_utterance(self) -> None:
        """Run final ASR on the full utterance and emit on_final."""
        # Use a window that covers the full utterance
        total = self._buffer.total_samples
        # Go a bit further back to capture speech start
        utterance_samples = total - self._speech_start_sample
        if utterance_samples < self.sample_rate * 0.2:
            self._buffer.clear()
            self._vad_offset = self._buffer.total_samples
            return

        audio = self._buffer.read_range(self._speech_start_sample, total)
        text = await self._transcribe_async(audio)
        text = text.strip()

        if text and self._on_final:
            await self._emit(self._on_final, text)

        # Clear processed audio from buffer (but keep recent for overlap)
        self._buffer.clear()
        self._vad_offset = self._buffer.total_samples

    async def _transcribe_async(self, audio: np.ndarray) -> str:
        """Run the transcribe callable in a thread and return text."""
        # Write to temp WAV
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
        try:
            sf.write(tmp_path, audio, self.sample_rate)
            loop = asyncio.get_running_loop()
            text = await loop.run_in_executor(
                self._executor, self._transcribe, tmp_path
            )
            return text
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    @staticmethod
    async def _emit(cb: PartialCallback | FinalCallback, text: str) -> None:
        """Call a callback that may be sync or async."""
        result = cb(text)
        if asyncio.iscoroutine(result):
            await result
