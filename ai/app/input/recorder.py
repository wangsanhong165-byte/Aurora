"""Audio stream capture — wraps sounddevice InputStream."""

from pathlib import Path
import numpy as np
import sounddevice as sd
import soundfile as sf


class AudioRecorder:
    """Capture microphone audio via InputStream callback."""

    _MIN_RATE = 8000

    def __init__(self, sample_rate: int = 16000, frame_size: int = 480) -> None:
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self._stream: sd.InputStream | None = None
        self._buffer: list[np.ndarray] = []

    def start(self) -> None:
        self._buffer = []
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.frame_size,
            callback=self._on_frame,
        )
        self._stream.start()

    def stop(self) -> np.ndarray | None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if self._buffer:
            audio = np.concatenate(self._buffer)
            self._buffer = []
            return audio
        return None

    @property
    def duration(self) -> float:
        total = sum(len(chunk) for chunk in self._buffer)
        return total / self.sample_rate

    def _on_frame(self, indata: np.ndarray, _frames: int, _time, _status) -> None:
        mono = indata if indata.ndim == 1 else indata[:, 0]
        self._buffer.append(mono.copy())

    def save(self, path: Path, audio: np.ndarray | None = None) -> Path:
        data = audio if audio is not None else np.concatenate(self._buffer) if self._buffer else np.zeros(0)
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(path), data, self.sample_rate)
        return path
