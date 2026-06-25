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
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

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


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "module": "tts",
        "engine": DEFAULT_TTS_ENGINE,
        "available_engines": TTSFactory.list_engines(),
    }


@app.post("/v1/tts/speak", response_model=TTSResponse)
def speak_text(request: TTSRequest) -> TTSResponse:
    try:
        engine = TTSFactory.create(_resolve_engine(request), config=_get_tts_config(_resolve_engine(request)))
        opts = request.model_dump(exclude={"text", "engine"}, exclude_none=True)
        return engine.speak(request.text, **opts)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/v1/tts/synthesize")
async def synthesize_endpoint(req: dict) -> Response:
    """Return raw WAV bytes — used by HTTPTTSAdapter.synthesize()."""
    text = req.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is empty")
    try:
        engine = TTSFactory.create(config=_get_tts_config())
        opts = {k: v for k, v in req.items() if k != "text"}
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
    parser.add_argument("--port", type=int, default=8030)
    args = parser.parse_args()
    load_env_file(Path(args.env_file))
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_config=UVICORN_LOG_CONFIG)


if __name__ == "__main__":
    main()
