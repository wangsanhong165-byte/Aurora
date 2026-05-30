import argparse
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

from app.core.config import DEFAULT_AUDIO_PATH
from app.core.schemas import RecordRequest, RecordResponse, VADListenRequest, VADListenResponse


app = FastAPI(title="Recorder API", version="1.1.0")


def record_microphone(output_path: Path, seconds: float, sample_rate: int) -> Path:
    try:
        import sounddevice
        import soundfile
    except ImportError as exc:
        raise RuntimeError("Missing recorder dependencies. Install: pip install sounddevice soundfile") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    audio = sounddevice.rec(
        int(seconds * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
    )
    sounddevice.wait()
    soundfile.write(str(output_path), audio, sample_rate)
    return output_path


def record_vad(
    output_path: Path,
    sample_rate: int = 16000,
    silence_timeout: float = 1.5,
    speech_threshold: float = 0.5,
    max_duration: float = 30.0,
    aggressiveness: int = 2,
) -> tuple[Path, float, bool]:
    """Record microphone using webrtcvad: only capture when speech is detected.

    Returns (path, duration_seconds, triggered).
    """
    try:
        import numpy as np
        import sounddevice as sd
        import soundfile as sf
        import webrtcvad
    except ImportError as exc:
        raise RuntimeError(
            "Missing VAD dependencies. Install: pip install sounddevice soundfile webrtcvad numpy"
        ) from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # webrtcvad works on 10/20/30ms frames; use 30ms at 16kHz = 480 samples
    frame_duration_ms = 30
    frame_size = int(sample_rate * frame_duration_ms / 1000)  # 480

    vad = webrtcvad.Vad(aggressiveness)

    # Buffers
    ring_buffer: list[bytes] = []        # rolling pre-speech buffer
    pre_speech_frames = int(0.5 * 1000 / frame_duration_ms)  # keep 0.5s before trigger
    speech_frames: list[np.ndarray] = []  # recorded speech as float32
    triggered = False
    silent_frames = 0
    voiced_frames = 0
    trigger_threshold = int(0.2 * 1000 / frame_duration_ms)  # ~7 frames of speech to trigger
    silence_threshold = int(silence_timeout * 1000 / frame_duration_ms)
    max_frames = int(max_duration * 1000 / frame_duration_ms)

    print("[VAD] Listening... (speak to trigger)")

    def audio_callback(indata: np.ndarray, frames: int, time_info, status):
        nonlocal triggered, silent_frames, voiced_frames

        if status:
            print(f"[VAD] stream status: {status}")

        # Convert float32 [-1,1] to int16 PCM for webrtcvad
        pcm = (indata[:, 0] * 32767).astype(np.int16).tobytes()
        is_speech = vad.is_speech(pcm, sample_rate)

        ring_buffer.append(pcm)
        if len(ring_buffer) > pre_speech_frames:
            ring_buffer.pop(0)

        if not triggered:
            if is_speech:
                voiced_frames += 1
            else:
                voiced_frames = max(0, voiced_frames - 1)

            if voiced_frames >= trigger_threshold:
                triggered = True
                silent_frames = 0
                # Flush ring buffer into speech buffer
                for buf in ring_buffer:
                    speech_frames.append(
                        np.frombuffer(buf, dtype=np.int16).astype(np.float32) / 32767.0
                    )
                ring_buffer.clear()
                print("[VAD] Speech detected, recording...")
        else:
            speech_frames.append(indata[:, 0].copy())
            if is_speech:
                silent_frames = 0
            else:
                silent_frames += 1

    try:
        with sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            blocksize=frame_size,
            callback=audio_callback,
        ):
            while True:
                sd.sleep(50)  # 50ms poll
                if triggered:
                    if silent_frames >= silence_threshold:
                        print(f"[VAD] Silence for {silence_timeout:.1f}s, stopping.")
                        break
                    if len(speech_frames) >= max_frames:
                        print(f"[VAD] Max duration {max_duration:.0f}s reached.")
                        break
                else:
                    # Safety: if listening too long without speech
                    if len(speech_frames) == 0 and len(ring_buffer) > 0:
                        # Just keep listening
                        pass
    except KeyboardInterrupt:
        pass

    if not triggered or len(speech_frames) == 0:
        print("[VAD] No speech detected.")
        # Write empty placeholder
        silence = __import__("numpy").zeros(int(0.1 * sample_rate), dtype="float32")
        sf.write(str(output_path), silence, sample_rate)
        return output_path, 0.0, False

    audio = np.concatenate(speech_frames)
    duration = len(audio) / sample_rate
    sf.write(str(output_path), audio, sample_rate)
    print(f"[VAD] Recorded {duration:.1f}s → {output_path}")
    return output_path, duration, True


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "module": "recorder"}


@app.post("/v1/audio/record", response_model=RecordResponse)
def record(request: RecordRequest) -> RecordResponse:
    try:
        output_path = Path(request.output_path) if request.output_path else DEFAULT_AUDIO_PATH
        audio_path = record_microphone(output_path, request.seconds, request.sample_rate)
        return RecordResponse(
            ok=True,
            audio_path=str(audio_path),
            seconds=request.seconds,
            sample_rate=request.sample_rate,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/v1/audio/listen", response_model=VADListenResponse)
def listen_vad(request: VADListenRequest) -> VADListenResponse:
    """Continuously listen and record only when speech is detected (VAD-based)."""
    try:
        output_path = Path(request.output_path) if request.output_path else DEFAULT_AUDIO_PATH
        audio_path, duration, triggered = record_vad(
            output_path=output_path,
            sample_rate=request.sample_rate,
            silence_timeout=request.silence_timeout,
            speech_threshold=request.speech_threshold,
            max_duration=request.max_duration,
            aggressiveness=request.aggressiveness,
        )
        return VADListenResponse(
            ok=True,
            audio_path=str(audio_path),
            duration=duration,
            sample_rate=request.sample_rate,
            triggered=triggered,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Microphone recorder API service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
