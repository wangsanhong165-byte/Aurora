import argparse
import tempfile
from pathlib import Path
from typing import Any

import torch
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from qwen_asr import Qwen3ASRModel

from app.core.config import DEFAULT_MODEL_DIR
from app.core.schemas import ASRRequest, ASRResponse, ASRResult


app = FastAPI(title="Local Qwen3-ASR API", version="1.0.0")

_model: Qwen3ASRModel | None = None
_model_dir: Path = DEFAULT_MODEL_DIR


def load_model() -> Qwen3ASRModel:
    global _model
    if _model is not None:
        return _model

    if not _model_dir.exists():
        raise RuntimeError(f"Model directory not found: {_model_dir}")

    device_map = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32

    _model = Qwen3ASRModel.from_pretrained(
        str(_model_dir),
        torch_dtype=dtype,
        device_map=device_map,
        low_cpu_mem_usage=True,
        max_inference_batch_size=1,
        max_new_tokens=256,
    )
    return _model


def result_to_model(result: Any) -> ASRResult:
    return ASRResult(
        text=getattr(result, "text", ""),
        language=getattr(result, "language", None),
    )


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "module": "asr",
        "model_dir": str(_model_dir),
        "model_loaded": _model is not None,
        "cuda_available": torch.cuda.is_available(),
        "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
    }


@app.post("/v1/asr/transcriptions", response_model=ASRResponse)
async def transcribe_upload(
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
) -> ASRResponse:
    suffix = Path(file.filename or "audio.wav").suffix or ".wav"

    try:
        model = load_model()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(await file.read())

        results = model.transcribe(audio=str(temp_path), language=language)
        return ASRResponse(ok=True, filename=file.filename, result=result_to_model(results[0]))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        if "temp_path" in locals() and temp_path.exists():
            temp_path.unlink(missing_ok=True)


@app.post("/v1/asr/transcriptions/by-path", response_model=ASRResponse)
def transcribe_path(
    audio_path: str = Form(...),
    language: str | None = Form(default=None),
) -> ASRResponse:
    return transcribe_json(ASRRequest(audio_path=audio_path, language=language))


@app.post("/v1/asr/transcribe", response_model=ASRResponse)
def transcribe_json(request: ASRRequest) -> ASRResponse:
    path = Path(request.audio_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Audio file not found: {request.audio_path}")

    try:
        model = load_model()
        results = model.transcribe(audio=str(path), language=request.language)
        return ASRResponse(ok=True, audio_path=str(path), result=result_to_model(results[0]))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local Qwen3-ASR API service")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args()


def main() -> None:
    global _model_dir
    args = parse_args()
    _model_dir = args.model_dir

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
