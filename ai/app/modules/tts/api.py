"""TTS API -- multi-engine router.

Set TTS_ENGINE in .env to switch:
  qwen3-tts   -> local Qwen3TTS model
  gsvi         -> legacy GPT-SoVITS (OpenAI-compatible HTTP)
  gsvi-v2pro   -> GPT-SoVITS v2Pro nvidia50 (/tts endpoint)
  edge-tts     -> Microsoft Edge TTS (cloud, free)
  cloud-tts    -> external cloud TTS API
  pyttsx3      -> system TTS fallback
"""

import argparse
import asyncio
import hashlib
import io
import os
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import requests
import soundfile as sf
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from app.core.config import (
    UVICORN_LOG_CONFIG, DEFAULT_ENV_PATH, DEFAULT_TTS_ENGINE,
    DEFAULT_TTS_OUTPUT_DIR, GSVI_URL, load_env_file,
)
from app.core.schemas import TTSRequest, TTSResponse
from app.modules.tts.engines import edge, gsvi, gsvi_v2


app = FastAPI(title="Local TTS API", version="3.0.0")

# ================================================================
#  helpers (shared)
# ================================================================
def env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return v.strip().lower() in {"1", "true", "yes", "on"} if v else default


def env_float(name: str, default: float) -> float:
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def tts_engine(request: TTSRequest | None = None) -> str:
    return (request.engine if request else None) or os.environ.get("TTS_ENGINE") or DEFAULT_TTS_ENGINE


def output_path(text: str, audio: bytes, suffix: str) -> Path:
    d = Path(os.environ.get("TTS_OUTPUT_DIR", str(DEFAULT_TTS_OUTPUT_DIR)))
    d.mkdir(parents=True, exist_ok=True)
    digest = hashlib.md5(text.encode() + audio).hexdigest()
    return d / f"{digest}.{suffix}"


def play_audio_bytes(audio: bytes) -> bool:
    if not audio:
        return False
    import sounddevice as sd
    data, sr = sf.read(io.BytesIO(audio), dtype="float32")
    sd.play(data, sr)
    sd.wait()
    return True


# ================================================================
#  engine 1: pyttsx3 (system TTS fallback)
# ================================================================
def _speak_pyttsx3(text: str) -> TTSResponse:
    if not text.strip():
        return TTSResponse(ok=True, spoken=False, text=text, engine="pyttsx3")
    import pyttsx3
    eng = pyttsx3.init()
    eng.say(text)
    eng.runAndWait()
    return TTSResponse(ok=True, spoken=True, text=text, engine="pyttsx3")


# ================================================================
#  engine 2: gsvi (legacy GPT-SoVITS, OpenAI-compatible API)
# ================================================================
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


def _map(raw: str, mapping: dict[str, str], fallback: str) -> str:
    return mapping.get(raw.strip().lower(), raw.strip() or fallback)


def _speak_gsvi(request: TTSRequest) -> TTSResponse:
    text = request.text.strip()
    if not text:
        return TTSResponse(ok=True, spoken=False, text=text, engine="gsvi")
    gsvi_url = os.environ.get("GSVI_URL", GSVI_URL).rstrip("/")
    payload = {
        "model": request.model or os.environ.get("GSVI_MODEL", "GSVI-v4"),
        "input": text,
        "voice": request.voice or os.environ.get("GSVI_VOICE", ""),
        "response_format": request.response_format or os.environ.get("GSVI_RESPONSE_FORMAT", "wav"),
        "speed": request.speed if request.speed is not None else env_float("GSVI_SPEED", 1.0),
        "other_params": {
            "text_lang": _map(request.text_lang or os.environ.get("GSVI_TEXT_LANG", "中英混合"), _TEXT_LANG_MAP, "中英混合"),
            "prompt_lang": _map(request.prompt_lang or os.environ.get("GSVI_PROMPT_LANG", "中文"), _PROMPT_LANG_MAP, "中文"),
            "emotion": _map(request.emotion or os.environ.get("GSVI_EMOTION", "默认"), _EMOTION_MAP, "默认"),
        },
    }
    r = requests.post(f"{gsvi_url}/v1/audio/speech", json=payload,
                      timeout=env_float("GSVI_TIMEOUT", 180))
    r.raise_for_status()
    if "application/json" in r.headers.get("content-type", ""):
        raise RuntimeError(str(r.json().get("error") or r.json()))
    audio_path = output_path(text, r.content, "wav")
    audio_path.write_bytes(r.content)
    spoken = play_audio_bytes(r.content)
    return TTSResponse(ok=True, spoken=spoken, text=text, engine="gsvi",
                       voice=payload["voice"], emotion=payload["other_params"]["emotion"],
                       audio_path=str(audio_path))


# ================================================================
#  engine 3: gsvi-v2pro (GPT-SoVITS v2Pro nvidia50)
# ================================================================
def _speak_gsvi_v2pro(request: TTSRequest) -> TTSResponse:
    text = request.text.strip()
    if not text:
        return TTSResponse(ok=True, spoken=False, text=text, engine="gsvi-v2pro")
    audio = gsvi_v2.synthesize(
        text,
        ref_audio_path=request.ref_audio_path or os.environ.get("GSVI_REF_AUDIO", ""),
        prompt_text=request.prompt_text or os.environ.get("GSVI_PROMPT_TEXT", ""),
        prompt_lang=request.prompt_lang or os.environ.get("GSVI_PROMPT_LANG", ""),
        text_lang=request.text_lang or os.environ.get("GSVI_TEXT_LANG", ""),
        speed_factor=request.speed if request.speed is not None else env_float("GSVI_SPEED", 1.0),
        gpt_weights=os.environ.get("GSVI_GPT_WEIGHTS", ""),
        sovits_weights=os.environ.get("GSVI_SOVITS_WEIGHTS", ""),
    )
    audio_path = output_path(text, audio, "wav")
    audio_path.write_bytes(audio)
    spoken = play_audio_bytes(audio)
    return TTSResponse(ok=True, spoken=spoken, text=text, engine="gsvi-v2pro",
                       engine_type="gsvi-v2pro", audio_path=str(audio_path))


# ================================================================
#  engine 4: qwen3-tts (local Qwen3TTS model)
# ================================================================
_qwen_model: Any = None
_MODELS_ROOT = Path(__file__).resolve().parents[3] / "models" / "tts"
_QWEN_MODEL_DIR = Path(os.environ.get("TTS_MODEL_DIR", str(_MODELS_ROOT / "Qwen3-TTS-12Hz-0.6B-Base")))
_voice_clone_prompt: Any = None


def _load_qwen_model() -> Any:
    global _qwen_model, _voice_clone_prompt
    if _qwen_model is not None:
        return _qwen_model
    os.environ.setdefault("NUMBA_CACHE_DIR", os.path.join(os.environ.get("TEMP", "/tmp"), "numba_cache"))
    import torch
    from qwen_tts import Qwen3TTSModel
    if not _QWEN_MODEL_DIR.exists():
        raise RuntimeError(f"Qwen3TTS model not found: {_QWEN_MODEL_DIR}")
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if device.startswith("cuda") else torch.float32
    print(f"[TTS] Loading Qwen3TTS from {_QWEN_MODEL_DIR} (device={device}, dtype={dtype})")
    _qwen_model = Qwen3TTSModel.from_pretrained(str(_QWEN_MODEL_DIR), device_map=device, dtype=dtype)
    print("[TTS] Qwen3TTS loaded")
    ref_audio = os.environ.get("TTS_REF_AUDIO", "")
    ref_text = os.environ.get("TTS_REF_TEXT", "")
    if ref_audio:
        try:
            _voice_clone_prompt = _qwen_model.create_voice_clone_prompt(
                ref_audio=ref_audio, ref_text=ref_text if ref_text else None, x_vector_only_mode=True)
            print(f"[TTS] Voice clone prompt cached ({ref_audio})")
        except Exception as exc:
            print(f"[TTS] Clone prompt failed: {exc}")
    return _qwen_model


def _synthesize_qwen(text: str, speaker: str = "", language: str = "") -> bytes:
    model = _load_qwen_model()
    lang = language or os.environ.get("TTS_LANGUAGE", "zh")
    lang_map = {"zh": "Chinese", "cn": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean"}
    lang_label = lang_map.get(lang.lower(), "Chinese")
    ref_audio = os.environ.get("TTS_REF_AUDIO", "")
    if not ref_audio:
        raise RuntimeError("TTS_REF_AUDIO not set")
    global _voice_clone_prompt
    t_start = time.time()
    if _voice_clone_prompt is not None:
        result = model.generate_voice_clone(text=text, language=lang_label,
            voice_clone_prompt=_voice_clone_prompt, max_new_tokens=160,
            do_sample=False, non_streaming_mode=True)
    else:
        ref_text = os.environ.get("TTS_REF_TEXT", "")
        result = model.generate_voice_clone(text=text, language=lang_label,
            ref_audio=ref_audio, ref_text=ref_text, max_new_tokens=160,
            do_sample=False, non_streaming_mode=True)
    print(f"[TTS] qwen generate: {time.time()-t_start:.1f}s")
    wavs_list, sr = result
    wavs = np.asarray(wavs_list[0], dtype=np.float32)
    if wavs.ndim == 2:
        wavs = wavs.flatten()
    buf = io.BytesIO()
    sf.write(buf, wavs, sr, format="WAV")
    return buf.getvalue()


def _speak_qwen(request: TTSRequest) -> TTSResponse:
    audio = _synthesize_qwen(request.text)
    audio_path = output_path(request.text, audio, "wav")
    audio_path.write_bytes(audio)
    spoken = play_audio_bytes(audio)
    return TTSResponse(ok=True, spoken=spoken, text=request.text, engine="qwen3-tts",
                       voice=os.environ.get("TTS_SPEAKER", "serena"), audio_path=str(audio_path))


# ================================================================
#  engine 5: edge-tts (Microsoft cloud TTS, free)
# ================================================================
def _speak_edge(request: TTSRequest) -> TTSResponse:
    text = request.text.strip()
    if not text:
        return TTSResponse(ok=True, spoken=False, text=text, engine="edge-tts")
    if request.voice:
        os.environ["TTS_EDGE_VOICE"] = request.voice
    audio = edge.synthesize(text)
    audio_path = output_path(text, audio, "wav")
    audio_path.write_bytes(audio)
    spoken = play_audio_bytes(audio)
    return TTSResponse(ok=True, spoken=spoken, text=text, engine="edge-tts",
                       voice=voice, audio_path=str(audio_path))


# ================================================================
#  engine 6: cloud-tts (external cloud TTS API)
# ================================================================
def _speak_cloud_tts(request: TTSRequest) -> TTSResponse:
    text = request.text.strip()
    if not text:
        return TTSResponse(ok=True, spoken=False, text=text, engine="cloud-tts")
    api_url = os.environ.get("TTS_API_URL", "").rstrip("/")
    api_key = os.environ.get("TTS_API_KEY", "")
    if not api_url:
        raise RuntimeError("TTS_API_URL not set in .env")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    headers["Content-Type"] = "application/json"
    payload = {
        "model": request.model or os.environ.get("TTS_CLOUD_MODEL", "tts-1"),
        "input": text,
        "voice": request.voice or os.environ.get("TTS_CLOUD_VOICE", "alloy"),
        "response_format": request.response_format or "wav",
        "speed": request.speed if request.speed is not None else 1.0,
    }
    r = requests.post(f"{api_url}/audio/speech", json=payload, headers=headers,
                      timeout=env_float("TTS_CLOUD_TIMEOUT", 60))
    r.raise_for_status()
    audio_path = output_path(text, r.content, "wav")
    audio_path.write_bytes(r.content)
    spoken = play_audio_bytes(r.content)
    return TTSResponse(ok=True, spoken=spoken, text=text, engine="cloud-tts",
                       voice=payload["voice"], audio_path=str(audio_path))


# ================================================================
#  main router
# ================================================================
def speak(request: TTSRequest) -> TTSResponse:
    engine = tts_engine(request)
    text_preview = request.text[:40].replace("\n", " ")
    print(f"[TTS] speak engine={engine} text='{text_preview}...'")

    # 1. pyttsx3
    if engine == "pyttsx3":
        return _speak_pyttsx3(request.text)

    # 2. gsvi (legacy)
    if engine == "gsvi":
        try:
            return _speak_gsvi(request)
        except Exception:
            if env_bool("TTS_FALLBACK_TO_PYTTSX3", True):
                return _speak_pyttsx3(request.text)
            raise

    # 3. gsvi-v2pro
    if engine == "gsvi-v2pro":
        try:
            return _speak_gsvi_v2pro(request)
        except Exception:
            if env_bool("TTS_FALLBACK_TO_PYTTSX3", True):
                return _speak_pyttsx3(request.text)
            raise

    # 4. qwen3-tts
    if engine == "qwen3-tts":
        try:
            return _speak_qwen(request)
        except Exception:
            if env_bool("TTS_FALLBACK_TO_PYTTSX3", True):
                return _speak_pyttsx3(request.text)
            raise

    # 5. edge-tts
    if engine == "edge-tts":
        try:
            return _speak_edge(request)
        except Exception:
            if env_bool("TTS_FALLBACK_TO_PYTTSX3", True):
                return _speak_pyttsx3(request.text)
            raise

    # 6. cloud-tts
    if engine == "cloud-tts":
        try:
            return _speak_cloud_tts(request)
        except Exception:
            if env_bool("TTS_FALLBACK_TO_PYTTSX3", True):
                return _speak_pyttsx3(request.text)
            raise

    raise RuntimeError(f"Unsupported TTS engine: {engine}")


# ================================================================
#  endpoints
# ================================================================
@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "module": "tts",
        "engine": tts_engine(),
        "qwen_model_loaded": _qwen_model is not None,
        "gsvi_url": os.environ.get("GSVI_URL", GSVI_URL),
    }


@app.post("/v1/tts/speak", response_model=TTSResponse)
def speak_text(request: TTSRequest) -> TTSResponse:
    try:
        return speak(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/v1/tts/synthesize")
async def synthesize_endpoint(req: dict) -> Response:
    """Return raw WAV bytes -- used by orchestrator for streaming playback."""
    text = req.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is empty")
    try:
        engine = tts_engine()

        # 1. pyttsx3 (no raw bytes, synthesize via qwen as fallback)
        if engine == "pyttsx3":
            audio = await asyncio.to_thread(_synthesize_qwen, text)
            return Response(content=audio, media_type="audio/wav")

        # 2. gsvi (legacy)
        if engine == "gsvi":
            gsvi_url = os.environ.get("GSVI_URL", GSVI_URL).rstrip("/")
            payload = {
                "model": os.environ.get("GSVI_MODEL", "GSVI-v4"),
                "input": text,
                "voice": os.environ.get("GSVI_VOICE", ""),
                "response_format": "wav",
                "speed": float(os.environ.get("GSVI_SPEED", "1.0")),
                "other_params": {
                    "text_lang": os.environ.get("GSVI_TEXT_LANG", "涓嫳娣峰悎"),
                    "prompt_lang": os.environ.get("GSVI_PROMPT_LANG", "涓枃"),
                    "emotion": os.environ.get("GSVI_EMOTION", "榛樿"),
                },
            }
            r = requests.post(f"{gsvi_url}/v1/audio/speech", json=payload, timeout=180)
            r.raise_for_status()
            return Response(content=r.content, media_type="audio/wav")

        # 3. gsvi-v2pro
        if engine == "gsvi-v2pro":
            audio = await asyncio.to_thread(gsvi_v2.synthesize, text,
                ref_audio_path=os.environ.get("GSVI_REF_AUDIO", ""),
                prompt_text=os.environ.get("GSVI_PROMPT_TEXT", ""),
                prompt_lang=os.environ.get("GSVI_PROMPT_LANG", ""),
                text_lang=os.environ.get("GSVI_TEXT_LANG", ""),
                speed_factor=float(os.environ.get("GSVI_SPEED", "1.0")),
                gpt_weights=os.environ.get("GSVI_GPT_WEIGHTS", ""),
                sovits_weights=os.environ.get("GSVI_SOVITS_WEIGHTS", ""),
            )
            return Response(content=audio, media_type="audio/wav")

        # 4. qwen3-tts
        if engine == "qwen3-tts":
            speaker = req.get("speaker", "")
            language = req.get("language", "")
            audio = await asyncio.to_thread(_synthesize_qwen, text, speaker, language)
            return Response(content=audio, media_type="audio/wav")

        # 5. edge-tts
        if engine == "edge-tts":
            audio = await asyncio.to_thread(edge.synthesize, text)
            return Response(content=audio, media_type="audio/wav")

        # 6. cloud-tts
        if engine == "cloud-tts":
            api_url = os.environ.get("TTS_API_URL", "").rstrip("/")
            api_key = os.environ.get("TTS_API_KEY", "")
            if not api_url:
                raise RuntimeError("TTS_API_URL not set")
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            headers["Content-Type"] = "application/json"
            r = requests.post(f"{api_url}/audio/speech", json={
                "model": os.environ.get("TTS_CLOUD_MODEL", "tts-1"),
                "input": text,
                "voice": os.environ.get("TTS_CLOUD_VOICE", "alloy"),
                "response_format": "wav",
            }, headers=headers, timeout=60)
            r.raise_for_status()
            return Response(content=r.content, media_type="audio/wav")

        # fallback
        audio = await asyncio.to_thread(_synthesize_qwen, text)
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
    uvicorn.run(app, host=args.host, port=args.port, log_config=UVICORN_LOG_CONFIG)


if __name__ == "__main__":
    main()
