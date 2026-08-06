"""TTS API — multi-engine router powered by TTSFactory.

Set TTS_ENGINE in .env to switch:
  qwen3-tts   -> local Qwen3TTS model
  gsvi         -> legacy GPT-SoVITS (OpenAI-compatible HTTP)
  gsvi-v2pro   -> GPT-SoVITS v2Pro nvidia50 (/tts endpoint)
  edge-tts     -> Microsoft Edge TTS (cloud, free)
  cloud-tts    -> external cloud TTS API
  pyttsx3      -> system TTS fallback
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import Response

from app.config_manager.service_config import service_config
from app.core.config import UVICORN_LOG_CONFIG, DEFAULT_ENV_PATH, DEFAULT_TTS_ENGINE, load_env_file
from app.core.schemas import TTSRequest, TTSResponse
from app.modules.tts.factory import TTSFactory
# Import engines so @TTSFactory.register decorators fire at import time
from app.modules.tts.engines import (  # noqa: F401
    EdgeTTS,
    GSVITTS,
    GSVIV2TTS,
    QwenTTS,
    Pyttsx3TTS,
    CloudTTS,
)


app = FastAPI(title="Local TTS API", version="3.1.0")

# Keep the selected engine alive for the lifetime of the service.  In
# particular, GSVI keeps its selected remote weights warm after startup.
_engines: dict[str, Any] = {}
_engine_error = ""
_engine_warm = False


def _resolve_engine(request: TTSRequest | None = None) -> str:
    """Return engine name: request.engine > env > DEFAULT_TTS_ENGINE."""
    if request and request.engine:
        return request.engine
    return DEFAULT_TTS_ENGINE


# ================================================================
#  Endpoints
# ================================================================


_config: Any = None


_engine_configs: dict = {}


def _get_tts_config(engine_name: str | None = None) -> Any:
    """Load TTS config for *engine_name*, or default engine if omitted."""
    global _engine_configs
    if not _engine_configs:
        try:
            from app.config_manager import load_and_validate
            cfg = load_and_validate()
            for eng_key in ("gsvi-v2pro", "qwen3-tts", "edge-tts", "pyttsx3", "cloud-tts"):
                eng = getattr(cfg.tts, eng_key.replace("-", "_"), None)
                if eng is not None:
                    _engine_configs[eng_key] = eng
            _engine_configs["_default"] = cfg.tts.engine
        except Exception as exc:
            print(f"[TTS] Config load skipped: {exc}")
            return None
    key = engine_name or _engine_configs.get("_default", "gsvi-v2pro")
    return _engine_configs.get(key)


def _get_engine(engine_name: str | None = None) -> Any:
    name = engine_name or DEFAULT_TTS_ENGINE
    if name not in _engines:
        _engines[name] = TTSFactory.create(name, config=_get_tts_config(name))
    return _engines[name]


@app.on_event("startup")
async def _preload_default_engine() -> None:
    """Create the default adapter before the first user request.

    The launcher performs an actual synthesis after GSVI is healthy, which
    loads the remote model weights onto the GPU.  This hook guarantees that
    the same adapter instance is reused for that warm-up and later requests.
    """
    global _engine_error
    try:
        _get_engine(DEFAULT_TTS_ENGINE)
        print(f"[TTS] Default engine ready: {DEFAULT_TTS_ENGINE}")
    except Exception as exc:
        _engine_error = str(exc)
        print(f"[TTS] Engine preload failed: {exc}")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": not _engine_error,
        "module": "tts",
        "engine": DEFAULT_TTS_ENGINE,
        "ready": DEFAULT_TTS_ENGINE in _engines,
        "warm": _engine_warm,
        "error": _engine_error or None,
        "available_engines": TTSFactory.list_engines(),
    }


@app.post("/warmup")
def warmup() -> dict[str, Any]:
    """Run one short synthesis so remote GPU kernels and caches are hot."""
    global _engine_warm, _engine_error
    if _engine_warm:
        return {"ok": True, "ready": True, "warm": True, "cached": True}
    try:
        engine = _get_engine(DEFAULT_TTS_ENGINE)
        audio = engine.synthesize("嗯。")
        if not audio:
            raise RuntimeError("warmup synthesis returned no audio")
        _engine_warm = True
        _engine_error = ""
        print(f"[TTS] Warmup complete: {DEFAULT_TTS_ENGINE} ({len(audio)} bytes)")
        return {"ok": True, "ready": True, "warm": True, "bytes": len(audio)}
    except Exception as exc:
        _engine_error = str(exc)
        print(f"[TTS] Warmup failed: {exc}")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/v1/tts/speak", response_model=TTSResponse)
def speak_text(request: TTSRequest) -> TTSResponse:
    try:
        engine = _get_engine(_resolve_engine(request))
        opts = request.model_dump(exclude={"text", "engine"}, exclude_none=True)
        return engine.speak(request.text, **opts)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/v1/tts/synthesize")
def synthesize_endpoint(req: dict = Body(...)) -> Response:
    """Return raw WAV bytes — used by HTTPTTSAdapter.synthesize()."""
    text = req.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is empty")
    try:
        engine = _get_engine(str(req.get("engine") or _resolve_engine()))
        opts = {k: v for k, v in req.items() if k not in {"text", "engine"}}
        audio = engine.synthesize(text, **opts)
        return Response(content=audio, media_type="audio/wav")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ================================================================
#  Entry point
# ================================================================


def main() -> None:
    parser = argparse.ArgumentParser(description="Local TTS API service")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int,
        default=os.environ.get("TTS_PORT", service_config.port("tts")))
    args = parser.parse_args()
    load_env_file(Path(args.env_file))
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_config=UVICORN_LOG_CONFIG)


if __name__ == "__main__":
    main()
