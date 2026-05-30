import argparse
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

from app.core.config import DEFAULT_AUDIO_PATH
from app.core.schemas import RecordRequest, RecordResponse


app = FastAPI(title="Recorder API", version="1.0.0")


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Microphone recorder API service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
