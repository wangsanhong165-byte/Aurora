"""ASR API router — powered by ASRFactory.

Engines:
  - qwen3-asr -> engines/qwen.py (local Qwen3ASR 1.7B)

Add new engines: create engines/xxx.py with a class decorated by @ASRFactory.register.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from app.config_manager.service_config import service_config
from app.core.config import UVICORN_LOG_CONFIG, DEFAULT_MODEL_DIR, DEFAULT_ASR_ENGINE, BASE_DIR
from app.core.schemas import ASRRequest, ASRResponse, ASRResult
from app.modules.asr.factory import ASRFactory
from app.modules.asr.engines import QwenASR  # noqa: F401 trigger registration


app = FastAPI(title="Local ASR API", version="2.1.0")

# ── Global engine (loaded once at startup, reused for all requests) ──
_engine: Any = None
_engine_ready = False
_engine_error = ""


@app.on_event("startup")
async def _preload_engine():
    """Preload the ASR model at startup so it's ready for the first request."""
    global _engine, _engine_ready, _engine_error
    try:
        print(f"[ASR] Preloading {DEFAULT_ASR_ENGINE} engine...")
        _engine = ASRFactory.create(config=get_asr_config())
        _engine.preload()
        _engine_ready = True
        print("[ASR] Engine ready")
    except Exception as exc:
        _engine_error = str(exc)
        print(f"[ASR] Engine preload failed: {exc}")


# ================================================================
#  Endpoints
# ================================================================


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": _engine_ready,
        "module": "asr",
        "engine": DEFAULT_ASR_ENGINE,
        "ready": _engine_ready,
        "error": _engine_error or None,
        "available_engines": ASRFactory.list_engines(),
    }


_config: Any = None


def get_asr_config() -> Any:
    """Lazy-load ASR config from conf.yaml."""
    global _config
    if _config is None:
        try:
            from app.config_manager import load_and_validate
            cfg = load_and_validate()
            _config = getattr(cfg.asr, cfg.asr.engine.replace("-", "_"), None)
        except Exception as exc:
            print(f"[ASR] Config load skipped: {exc}")
    return _config


@app.post("/v1/asr/transcriptions", response_model=ASRResponse)
async def transcribe_upload(
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
) -> ASRResponse:
    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    temp_path = None
    try:
        if not _engine_ready:
            raise HTTPException(status_code=503, detail=f"ASR not ready: {_engine_error}")
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
            temp_path = Path(tf.name)
            tf.write(await file.read())
        result = _engine.transcribe(str(temp_path), language)
        return ASRResponse(ok=True, filename=file.filename, result=ASRResult(**result))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


@app.post("/v1/asr/transcribe", response_model=ASRResponse)
def transcribe_json(request: ASRRequest) -> ASRResponse:
    path = Path(request.audio_path)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Audio file not found: {request.audio_path}",
        )
    try:
        if not _engine_ready:
            raise HTTPException(status_code=503, detail=f"ASR not ready: {_engine_error}")
        result = _engine.transcribe(str(path), request.language)
        return ASRResponse(ok=True, audio_path=str(path), result=ASRResult(**result))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ================================================================
#  Entry point
# ================================================================


def main() -> None:
    parser = argparse.ArgumentParser(description="Local ASR API service")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int,
        default=os.environ.get("ASR_PORT", service_config.port("asr")))
    args = parser.parse_args()
    cfg = get_asr_config()
    if cfg is not None:
        cfg.model_dir = str(args.model_dir)
    else:
        # Fallback: set env var so engine can read it
        os.environ.setdefault("ASR_MODEL_DIR", str(args.model_dir))
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_config=UVICORN_LOG_CONFIG)


if __name__ == "__main__":
    main()
