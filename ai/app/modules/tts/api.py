import argparse
import hashlib
import os
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, HTTPException

from app.core.config import DEFAULT_ENV_PATH, DEFAULT_TTS_ENGINE, DEFAULT_TTS_OUTPUT_DIR, GSVI_URL, load_env_file
from app.core.schemas import TTSRequest, TTSResponse


app = FastAPI(title="Local TTS API", version="1.1.0")


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def tts_engine(request: TTSRequest) -> str:
    return (request.engine or os.environ.get("TTS_ENGINE") or DEFAULT_TTS_ENGINE).lower()


def gsvi_options(request: TTSRequest) -> dict[str, Any]:
    return {
        "url": os.environ.get("GSVI_URL", GSVI_URL).rstrip("/"),
        "model": request.model or os.environ.get("GSVI_MODEL", "GSVI-v4"),
        "voice": request.voice or os.environ.get("GSVI_VOICE", "明日方舟-中文-阿米娅"),
        "emotion": request.emotion or os.environ.get("GSVI_EMOTION", "默认"),
        "text_lang": request.text_lang or os.environ.get("GSVI_TEXT_LANG", "中英混合"),
        "prompt_lang": request.prompt_lang or os.environ.get("GSVI_PROMPT_LANG", "中文"),
        "response_format": request.response_format or os.environ.get("GSVI_RESPONSE_FORMAT", "wav"),
        "speed": request.speed if request.speed is not None else env_float("GSVI_SPEED", 1.0),
        "timeout": env_float("GSVI_TIMEOUT", 180.0),
    }


def output_path(text: str, audio: bytes, suffix: str) -> Path:
    output_dir = Path(os.environ.get("TTS_OUTPUT_DIR", str(DEFAULT_TTS_OUTPUT_DIR)))
    output_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.md5(text.encode("utf-8") + audio).hexdigest()
    return output_dir / f"{digest}.{suffix}"


def play_audio_bytes(audio: bytes, audio_format: str) -> bool:
    if not audio:
        return False

    try:
        import sounddevice as sd
        import soundfile as sf
    except ImportError as exc:
        raise RuntimeError("Missing playback dependencies. Install: pip install sounddevice soundfile") from exc

    data, samplerate = sf.read(BytesIO(audio), dtype="float32")
    sd.play(data, samplerate)
    sd.wait()
    return True


def speak_with_pyttsx3(text: str) -> TTSResponse:
    if not text.strip():
        return TTSResponse(ok=True, spoken=False, text=text, engine="pyttsx3")
    try:
        import pyttsx3
    except ImportError as exc:
        raise RuntimeError("Missing TTS dependency. Install: pip install pyttsx3") from exc

    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()
    return TTSResponse(ok=True, spoken=True, text=text, engine="pyttsx3")


def synthesize_with_gsvi(request: TTSRequest) -> TTSResponse:
    text = request.text.strip()
    if not text:
        return TTSResponse(ok=True, spoken=False, text=request.text, engine="gsvi")

    options = gsvi_options(request)
    payload = {
        "model": options["model"],
        "input": text,
        "voice": options["voice"],
        "response_format": options["response_format"],
        "speed": options["speed"],
        "other_params": {
            "text_lang": options["text_lang"],
            "prompt_lang": options["prompt_lang"],
            "emotion": options["emotion"],
        },
    }

    response = requests.post(
        f"{options['url']}/v1/audio/speech",
        json=payload,
        timeout=options["timeout"],
    )
    response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        body = response.json()
        raise RuntimeError(str(body.get("error") or body))

    audio_format = str(options["response_format"]).lower()
    audio_path = output_path(text, response.content, audio_format)
    audio_path.write_bytes(response.content)
    spoken = play_audio_bytes(response.content, audio_format)

    return TTSResponse(
        ok=True,
        spoken=spoken,
        text=request.text,
        engine="gsvi",
        voice=options["voice"],
        emotion=options["emotion"],
        audio_path=str(audio_path),
    )


def speak(request: TTSRequest) -> TTSResponse:
    engine = tts_engine(request)
    if engine == "pyttsx3":
        return speak_with_pyttsx3(request.text)
    if engine != "gsvi":
        raise RuntimeError(f"Unsupported TTS engine: {engine}")

    try:
        return synthesize_with_gsvi(request)
    except Exception:
        if env_bool("TTS_FALLBACK_TO_PYTTSX3", True):
            return speak_with_pyttsx3(request.text)
        raise


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "module": "tts",
        "engine": os.environ.get("TTS_ENGINE", DEFAULT_TTS_ENGINE),
        "gsvi_url": os.environ.get("GSVI_URL", GSVI_URL),
        "gsvi_model": os.environ.get("GSVI_MODEL", "GSVI-v4"),
        "gsvi_voice": os.environ.get("GSVI_VOICE", "明日方舟-中文-阿米娅"),
        "gsvi_emotion": os.environ.get("GSVI_EMOTION", "默认"),
    }


@app.post("/v1/tts/speak", response_model=TTSResponse)
def speak_text(request: TTSRequest) -> TTSResponse:
    try:
        return speak(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Local TTS API service")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8030)
    args = parser.parse_args()

    load_env_file(Path(args.env_file))

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
