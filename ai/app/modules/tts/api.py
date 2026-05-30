"""
TTS (Text-to-Speech) API Service

Supports two engines:
  - gsvi  : GPT-SoVITS high-quality neural TTS (local GPU)
  - pyttsx3: system default TTS (fallback)

Voice Configuration Guide
==========================
1. Leave GSVI_VOICE empty → auto-detect installed voice on startup
2. Set GSVI_VOICE=角色名 → use a specific voice (must match exactly)
3. Run GET /v1/tts/voices to list all available voices
4. Labels like "default"/"zh" are auto-mapped to GSVI Chinese labels

To add a new GSVI voice model:
  - Install it via the GSVI WebUI at http://127.0.0.1:8050
  - Or place model files under models/GPT-SoVITS-1007-cu128/models/v4/<角色名>/
  - Run GET /v1/tts/voices to verify it's detected
  - Set GSVI_VOICE=<角色名> in .env or leave empty for auto-detect
"""

import argparse
import hashlib
import json
import os
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, HTTPException

from app.core.config import DEFAULT_ENV_PATH, DEFAULT_TTS_ENGINE, DEFAULT_TTS_OUTPUT_DIR, GSVI_URL, load_env_file
from app.core.schemas import TTSRequest, TTSResponse


app = FastAPI(
    title="Local TTS API",
    version="1.2.0",
    description=__doc__.split("Voice Configuration Guide")[0].strip(),
)

# ══════════════════════════════════════════════════════════════════════
#  GSVI Label Mapping
#  GSVI 内部使用中文标签，这里把英文/简写自动映射过去
# ══════════════════════════════════════════════════════════════════════

_EMOTION_MAP: dict[str, str] = {
    "default": "默认",
    "happy": "开心",
    "sad": "悲伤",
    "angry": "愤怒",
    "surprise": "惊讶",
    "fear": "恐惧",
    "neutral": "中性",
    "calm": "平静",
    "excited": "激动",
    "serious": "严肃",
    "gentle": "温柔",
}

_TEXT_LANG_MAP: dict[str, str] = {
    "zh": "中英混合",
    "cn": "中英混合",
    "chinese": "中英混合",
    "mixed": "中英混合",
    "auto": "中英混合",
    "zh_en": "中英混合",
    "en": "英文",
    "english": "英文",
    "ja": "日文",
    "jp": "日文",
    "japanese": "日文",
    "ko": "韩文",
    "kr": "韩文",
    "korean": "韩文",
    "yue": "粤语",
    "cantonese": "粤语",
}

_PROMPT_LANG_MAP: dict[str, str] = {
    "zh": "中文",
    "cn": "中文",
    "chinese": "中文",
    "en": "英文",
    "english": "英文",
    "ja": "日文",
    "jp": "日文",
    "japanese": "日文",
    "ko": "韩文",
    "kr": "韩文",
    "korean": "韩文",
    "yue": "粤语",
    "cantonese": "粤语",
    "auto": "中文",
    "mixed": "中文",
    "zh_en": "中文",
}

# 缓存已检测到的音色，避免每次 TTS 都查 GSVI
_auto_voice_cache: str | None = None


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


def _map_label(raw: str | None, mapping: dict[str, str], fallback: str) -> str:
    """Map English short label to GSVI Chinese label. Already-Chinese labels pass through."""
    if not raw:
        return fallback
    key = raw.strip().lower()
    return mapping.get(key, raw.strip())


def _detect_gsvi_voice(gsvi_url: str, model: str = "GSVI-v4", timeout: float = 10.0) -> str:
    """
    Query GSVI for installed voice models and auto-select one.

    Priority:
      1. First voice containing "中文" (Chinese)
      2. First voice in the list
      3. Fallback: "明日方舟-中文-阿米娅"

    Returns the selected voice name string.
    """
    global _auto_voice_cache
    if _auto_voice_cache is not None:
        return _auto_voice_cache

    default_voice = "明日方舟-中文-阿米娅"

    # Extract version from model name (e.g. "GSVI-v4" → "v4")
    version = model.split("-")[-1] if "-" in model else "v4"

    try:
        resp = requests.get(
            f"{gsvi_url.rstrip('/')}/check_model/{version}",
            timeout=timeout,
        )
        resp.raise_for_status()
        installed = resp.json().get("installed", [])

        if installed:
            # Prefer Chinese voices
            for voice in installed:
                if "中文" in voice:
                    _auto_voice_cache = voice
                    print(f"[TTS] Auto-detected voice: {voice}")
                    return voice

            # Fallback: first installed voice
            _auto_voice_cache = installed[0]
            print(f"[TTS] Auto-detected voice: {installed[0]}")
            return installed[0]

    except Exception as exc:
        print(f"[TTS] Could not query GSVI for voices ({exc}), using default: {default_voice}")

    _auto_voice_cache = default_voice
    return default_voice


def _fetch_gsvi_voices(gsvi_url: str, timeout: float = 10.0) -> list[dict[str, Any]]:
    """Fetch list of all installed GSVI voices with their languages and emotions."""
    voices: list[dict[str, Any]] = []
    model = os.environ.get("GSVI_MODEL", "GSVI-v4")
    version = model.split("-")[-1] if "-" in model else "v4"

    try:
        # Get installed model names
        resp = requests.get(
            f"{gsvi_url.rstrip('/')}/check_model/{version}",
            timeout=timeout,
        )
        resp.raise_for_status()
        installed = resp.json().get("installed", [])

        for voice_name in installed:
            voice_info: dict[str, Any] = {"name": voice_name, "languages": [], "emotions": []}

            # Get supported languages for this voice
            try:
                # GSVI speaker list includes languages and emotions
                spk_resp = requests.get(
                    f"{gsvi_url.rstrip('/')}/speakers/{version}",
                    timeout=timeout,
                )
                spk_resp.raise_for_status()
                speakers = spk_resp.json().get("speakers", {})
                if voice_name in speakers:
                    lang_dict = speakers[voice_name]
                    for lang, emotions in lang_dict.items():
                        voice_info["languages"].append(lang)
                        for emo_file in emotions:
                            # Extract emotion from filename like "【开心】xxx.wav"
                            emo_name = "默认"
                            if "【" in emo_file and "】" in emo_file:
                                emo_name = emo_file.split("【")[1].split("】")[0]
                            if emo_name not in voice_info["emotions"]:
                                voice_info["emotions"].append(emo_name)
            except Exception:
                pass

            voices.append(voice_info)

    except Exception as exc:
        print(f"[TTS] Could not fetch voice list: {exc}")

    return voices


def gsvi_options(request: TTSRequest) -> dict[str, Any]:
    """
    Build GSVI request options with label mapping and voice auto-detection.

    Priority for each field:
      1. Request-level parameter (from API call)
      2. Environment variable (from .env)
      3. Default mapped value
    """
    gsvi_url = os.environ.get("GSVI_URL", GSVI_URL).rstrip("/")
    model = request.model or os.environ.get("GSVI_MODEL", "GSVI-v4")

    # Voice: request > env > auto-detect
    voice = request.voice or os.environ.get("GSVI_VOICE", "")
    if not voice:
        voice = _detect_gsvi_voice(gsvi_url, model)

    # Emotion: map English labels to Chinese
    emotion = _map_label(
        request.emotion or os.environ.get("GSVI_EMOTION", ""),
        _EMOTION_MAP,
        "默认",
    )

    # Text language (what the input text is)
    text_lang = _map_label(
        request.text_lang or os.environ.get("GSVI_TEXT_LANG", ""),
        _TEXT_LANG_MAP,
        "中英混合",
    )

    # Prompt language (what the reference audio's text is)
    prompt_lang = _map_label(
        request.prompt_lang or os.environ.get("GSVI_PROMPT_LANG", ""),
        _PROMPT_LANG_MAP,
        "中文",
    )

    return {
        "url": gsvi_url,
        "model": model,
        "voice": voice,
        "emotion": emotion,
        "text_lang": text_lang,
        "prompt_lang": prompt_lang,
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
    print(f"[TTS] Synthesizing with voice={options['voice']}, emotion={options['emotion']}, "
          f"text_lang={options['text_lang']}")

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

    try:
        response = requests.post(
            f"{options['url']}/v1/audio/speech",
            json=payload,
            timeout=options["timeout"],
        )
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"GSVI service unreachable at {options['url']}. "
            f"Start it with: python start_services.py --with-gsvi"
        )
    except requests.exceptions.HTTPError as exc:
        detail = ""
        try:
            detail = exc.response.json().get("error", {}).get("message", "")
        except Exception:
            detail = exc.response.text[:200] if exc.response else ""
        raise RuntimeError(
            f"GSVI synthesis failed (voice={options['voice']}, emotion={options['emotion']}). "
            f"{detail or str(exc)}"
        )

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
    except Exception as exc:
        print(f"[TTS] GSVI failed: {exc}")
        if env_bool("TTS_FALLBACK_TO_PYTTSX3", True):
            print("[TTS] Falling back to pyttsx3 (system default voice)")
            return speak_with_pyttsx3(request.text)
        raise


# ══════════════════════════════════════════════════════════════════════
#  API Endpoints
# ══════════════════════════════════════════════════════════════════════

@app.get("/health")
def health() -> dict[str, Any]:
    gsvi_url = os.environ.get("GSVI_URL", GSVI_URL).rstrip("/")
    model = os.environ.get("GSVI_MODEL", "GSVI-v4")
    raw_voice = os.environ.get("GSVI_VOICE", "")
    voice = raw_voice if raw_voice else _detect_gsvi_voice(gsvi_url, model)
    emotion = _map_label(os.environ.get("GSVI_EMOTION", ""), _EMOTION_MAP, "默认")
    return {
        "ok": True,
        "module": "tts",
        "engine": os.environ.get("TTS_ENGINE", DEFAULT_TTS_ENGINE),
        "gsvi_url": gsvi_url,
        "gsvi_model": model,
        "gsvi_voice": voice,
        "gsvi_emotion": emotion,
        "available_mappings": {
            "emotion": list(_EMOTION_MAP.keys()),
            "text_lang": list(_TEXT_LANG_MAP.keys()),
            "prompt_lang": list(_PROMPT_LANG_MAP.keys()),
        },
    }


@app.get("/v1/tts/voices")
def list_voices() -> dict[str, Any]:
    """
    List all available GSVI voice models with their languages and emotions.

    Use this to discover which voices you can set as GSVI_VOICE in .env
    or pass as --tts-voice to main.py.
    """
    gsvi_url = os.environ.get("GSVI_URL", GSVI_URL).rstrip("/")
    model = os.environ.get("GSVI_MODEL", "GSVI-v4")
    current = os.environ.get("GSVI_VOICE", "") or _detect_gsvi_voice(gsvi_url, model)

    try:
        voices = _fetch_gsvi_voices(gsvi_url)
    except Exception as exc:
        voices = []
        return {
            "ok": True,
            "current_voice": current,
            "voices": voices,
            "error": str(exc),
            "hint": "Make sure GSVI is running (python start_services.py --with-gsvi)",
        }

    return {
        "ok": True,
        "current_voice": current,
        "voices": voices,
        "hint": "Set GSVI_VOICE=<name> in .env to use a specific voice",
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
