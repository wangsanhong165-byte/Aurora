"""TTS API — supports Qwen3TTS (primary) and GSVI (legacy).

Routes based on TTS_ENGINE env var:
  - qwen3-tts → local Qwen3TTS 1.7B CustomVoice (8-bit)
  - gsvi      → GPT-SoVITS HTTP (:8050)
  - pyttsx3   → system TTS fallback
"""

import argparse
import hashlib
import io
import os
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from app.core.config import DEFAULT_ENV_PATH, DEFAULT_TTS_ENGINE, DEFAULT_TTS_OUTPUT_DIR, GSVI_URL, load_env_file
from app.core.schemas import TTSRequest, TTSResponse


app = FastAPI(title="Local TTS API", version="2.0.0")

# ── Qwen3TTS singleton ──────────────────────────────────────────
_qwen_model: Any = None
_QWEN_MODEL_DIR = Path(__file__).resolve().parents[3] / "models" / "tts" / "Qwen3-TTS-12Hz-1.7B-CustomVoice"

_SPEAKERS = ["serena", "vivian", "uncle_fu", "ryan", "aiden", "ono_anna", "sohee", "eric", "dylan"]


def _load_qwen_model() -> Any:
    global _qwen_model
    if _qwen_model is not None:
        return _qwen_model

    os.environ.setdefault("NUMBA_CACHE_DIR", os.path.join(os.environ.get("TEMP", "/tmp"), "numba_cache"))

    import torch
    from qwen_tts import Qwen3TTSModel

    if not _QWEN_MODEL_DIR.exists():
        raise RuntimeError(f"Qwen3TTS model not found: {_QWEN_MODEL_DIR}")

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    load_8bit = device.startswith("cuda") and os.environ.get("TTS_LOAD_8BIT", "1") == "1"

    print(f"[TTS] Loading Qwen3TTS from {_QWEN_MODEL_DIR} (device={device}, 8bit={load_8bit})")
    _qwen_model = Qwen3TTSModel.from_pretrained(
        str(_QWEN_MODEL_DIR),
        device_map=device,
        load_in_8bit=load_8bit,
    )
    print("[TTS] Qwen3TTS loaded")
    return _qwen_model


# ── GSVI helpers (unchanged) ────────────────────────────────────
_EMOTION_MAP = {
    "default": "默认", "happy": "开心", "sad": "悲伤",
    "angry": "愤怒", "surprise": "惊讶", "fear": "恐惧",
    "neutral": "中性", "calm": "平静", "excited": "激动",
    "serious": "严肃", "gentle": "温柔",
}
_TEXT_LANG_MAP = {
    "zh": "中英混合", "cn": "中英混合", "chinese": "中英混合",
    "mixed": "中英混合", "auto": "中英混合", "zh_en": "中英混合",
    "en": "英文", "english": "英文",
    "ja": "日文", "jp": "日文", "japanese": "日文",
    "ko": "韩文", "kr": "韩文", "korean": "韩文",
    "yue": "粤语", "cantonese": "粤语",
}
_PROMPT_LANG_MAP = {
    "zh": "中文", "cn": "中文", "chinese": "中文",
    "mixed": "中文", "auto": "中文", "zh_en": "中文",
    "en": "英文", "english": "英文",
    "ja": "日文", "jp": "日文", "japanese": "日文",
    "ko": "韩文", "kr": "韩文", "korean": "韩文",
    "yue": "粤语", "cantonese": "粤语",
}


def _map_label(raw: str, mapping: dict[str, str], fallback: str) -> str:
    key = raw.strip().lower()
    return mapping.get(key, raw.strip())


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


def tts_engine(request: TTSRequest | None = None) -> str:
    return (request.engine if request else None) or os.environ.get("TTS_ENGINE") or DEFAULT_TTS_ENGINE


# ── GSVI synthesis ──────────────────────────────────────────────
def gsvi_options(request: TTSRequest) -> dict[str, Any]:
    raw_emotion = request.emotion or os.environ.get("GSVI_EMOTION", "默认")
    raw_text_lang = request.text_lang or os.environ.get("GSVI_TEXT_LANG", "中英混合")
    raw_prompt_lang = request.prompt_lang or os.environ.get("GSVI_PROMPT_LANG", "中文")
    return {
        "url": os.environ.get("GSVI_URL", GSVI_URL).rstrip("/"),
        "model": request.model or os.environ.get("GSVI_MODEL", "GSVI-v4"),
        "voice": request.voice or os.environ.get("GSVI_VOICE", "明日方舟-中文-阿米娅"),
        "emotion": _map_label(raw_emotion, _EMOTION_MAP, "默认"),
        "text_lang": _map_label(raw_text_lang, _TEXT_LANG_MAP, "中英混合"),
        "prompt_lang": _map_label(raw_prompt_lang, _PROMPT_LANG_MAP, "中文"),
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
        raise RuntimeError("Missing playback dependencies") from exc
    data, sr = sf.read(io.BytesIO(audio), dtype="float32")
    sd.play(data, sr)
    sd.wait()
    return True


def speak_with_pyttsx3(text: str) -> TTSResponse:
    if not text.strip():
        return TTSResponse(ok=True, spoken=False, text=text, engine="pyttsx3")
    try:
        import pyttsx3
    except ImportError as exc:
        raise RuntimeError("Missing pyttsx3") from exc
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
    response = requests.post(f"{options['url']}/v1/audio/speech", json=payload, timeout=options["timeout"])
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        body = response.json()
        raise RuntimeError(str(body.get("error") or body))
    audio_format = str(options["response_format"]).lower()
    audio_path = output_path(text, response.content, audio_format)
    audio_path.write_bytes(response.content)
    spoken = play_audio_bytes(response.content, audio_format)
    return TTSResponse(ok=True, spoken=spoken, text=request.text, engine="gsvi",
                       voice=options["voice"], emotion=options["emotion"], audio_path=str(audio_path))


# ── Qwen3TTS synthesis ──────────────────────────────────────────
def synthesize_with_qwen(text: str, speaker: str = "", language: str = "") -> bytes:
    """Generate audio from text using Qwen3TTS. Returns raw WAV bytes."""
    model = _load_qwen_model()
    spk = speaker or os.environ.get("TTS_SPEAKER", "serena")
    lang = language or os.environ.get("TTS_LANGUAGE", "zh")
    lang_map = {"zh": "Chinese", "cn": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean"}
    lang_label = lang_map.get(lang.lower(), "Chinese")
    result = model.generate_custom_voice(text=text, language=lang_label, speaker=spk)
    if isinstance(result, tuple):
        wavs, sr = result
    else:
        import soundfile as sf
        wavs, sr = sf.read(str(result))
    buf = io.BytesIO()
    import soundfile as sf
    sf.write(buf, wavs, sr, format="WAV")
    return buf.getvalue()


# ── Routing ─────────────────────────────────────────────────────
def speak(request: TTSRequest) -> TTSResponse:
    engine = tts_engine(request)
    if engine == "pyttsx3":
        return speak_with_pyttsx3(request.text)
    if engine == "gsvi":
        try:
            return synthesize_with_gsvi(request)
        except Exception:
            if env_bool("TTS_FALLBACK_TO_PYTTSX3", True):
                return speak_with_pyttsx3(request.text)
            raise
    if engine == "qwen3-tts":
        try:
            audio = synthesize_with_qwen(request.text)
            audio_format = "wav"
            audio_path = output_path(request.text, audio, audio_format)
            audio_path.write_bytes(audio)
            spoken = play_audio_bytes(audio, audio_format)
            return TTSResponse(ok=True, spoken=spoken, text=request.text, engine="qwen3-tts",
                               voice=os.environ.get("TTS_SPEAKER", "serena"), audio_path=str(audio_path))
        except Exception:
            if env_bool("TTS_FALLBACK_TO_PYTTSX3", True):
                return speak_with_pyttsx3(request.text)
            raise
    raise RuntimeError(f"Unsupported TTS engine: {engine}")


# ── Endpoints ───────────────────────────────────────────────────
@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "module": "tts",
        "engine": tts_engine(),
        "qwen_model_loaded": _qwen_model is not None,
        "speakers": _SPEAKERS,
        "gsvi_url": os.environ.get("GSVI_URL", GSVI_URL),
    }


@app.post("/v1/tts/speak", response_model=TTSResponse)
def speak_text(request: TTSRequest) -> TTSResponse:
    try:
        return speak(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class SynthesizeRequest:
    """Minimal request for orchestrator's streaming path."""
    def __init__(self, text: str, speaker: str = "", language: str = ""):
        self.text = text
        self.speaker = speaker
        self.language = language


@app.post("/v1/tts/synthesize")
async def synthesize_endpoint(request: dict) -> Response:
    """Return raw WAV bytes — used by orchestrator for streaming playback."""
    text = request.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is empty")
    try:
        engine = tts_engine()
        if engine == "gsvi":
            # GSVI path
            gsvi_url = os.environ.get("GSVI_URL", GSVI_URL).rstrip("/")
            payload = {
                "model": os.environ.get("GSVI_MODEL", "GSVI-v4"),
                "input": text,
                "voice": os.environ.get("GSVI_VOICE", ""),
                "response_format": "wav",
                "speed": float(os.environ.get("GSVI_SPEED", "1.0")),
                "other_params": {
                    "text_lang": os.environ.get("GSVI_TEXT_LANG", "中英混合"),
                    "prompt_lang": os.environ.get("GSVI_PROMPT_LANG", "中文"),
                    "emotion": os.environ.get("GSVI_EMOTION", "默认"),
                },
            }
            r = requests.post(f"{gsvi_url}/v1/audio/speech", json=payload, timeout=180)
            r.raise_for_status()
            return Response(content=r.content, media_type="audio/wav")
        else:
            # Qwen3TTS path
            speaker = request.get("speaker", "")
            language = request.get("language", "")
            audio = synthesize_with_qwen(text, speaker=speaker, language=language)
            return Response(content=audio, media_type="audio/wav")
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