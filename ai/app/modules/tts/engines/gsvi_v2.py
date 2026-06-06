"""GSVI v2Pro engine -- GPT-SoVITS v2Pro nvidia50 HTTP API.

Endpoint: POST /tts
Returns raw WAV bytes.

Before each synthesis, calls /set_gpt_weights and /set_sovits_weights (GET)
to switch to the persona-specific model if configured.
"""

from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any

import requests

# ---- Language mapping for v2Pro API ----
_TEXT_LANG_MAP: dict[str, str] = {
    "zh": "zh", "cn": "zh", "chinese": "zh",
    "mixed": "zh", "auto": "zh", "zh_en": "zh",
    "en": "en", "english": "en",
    "ja": "ja", "jp": "ja", "japanese": "ja",
    "ko": "ko", "kr": "ko", "korean": "ko",
    "yue": "yue", "cantonese": "yue",
    # Chinese names (used by legacy code in run.py persona loading)
    "\u4e2d\u6587": "zh", "\u82f1\u6587": "en", "\u65e5\u6587": "ja", "\u65e5\u8bed": "ja",
    "\u97e9\u6587": "ko", "\u97e9\u8bed": "ko", "\u7ca4\u8bed": "yue",
}

# ---- Base dirs ----
_AI_DIR = Path(__file__).resolve().parents[4]  # c++/ai/
_GSVI_DIR = _AI_DIR / "models" / "tts" / "GPT-SoVITS-v2pro-20250604-nvidia50"


def _infer_text_lang(text: str) -> str:
    """Quick heuristic: if text contains CJK characters, default to zh."""
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff' or '\u3040' <= ch <= '\u30ff':
            return "zh"
    return "en"


def _map_lang(raw: str, mapping: dict[str, str]) -> str:
    return mapping.get(raw.strip().lower(), raw.strip().lower())


def _gsvi_url() -> str:
    return os.environ.get("GSVI_URL", "http://127.0.0.1:8050").rstrip("/")


def _set_model_weights(gpt_path: str, sovits_path: str) -> None:
    """Switch GSVI v2Pro to persona-specific model weights via GET endpoints."""
    base = _gsvi_url()
    if gpt_path:
        try:
            r = requests.get(f"{base}/set_gpt_weights", params={"weights_path": gpt_path}, timeout=10)
            if r.status_code == 200:
                print(f"[GSVI-v2pro] set_gpt_weights OK: {gpt_path}")
            else:
                print(f"[GSVI-v2pro] set_gpt_weights FAIL {r.status_code}: {r.text[:200]}")
        except Exception as exc:
            print(f"[GSVI-v2pro] set_gpt_weights error: {exc}")
    if sovits_path:
        try:
            r = requests.get(f"{base}/set_sovits_weights", params={"weights_path": sovits_path}, timeout=10)
            if r.status_code == 200:
                print(f"[GSVI-v2pro] set_sovits_weights OK: {sovits_path}")
            else:
                print(f"[GSVI-v2pro] set_sovits_weights FAIL {r.status_code}: {r.text[:200]}")
        except Exception as exc:
            print(f"[GSVI-v2pro] set_sovits_weights error: {exc}")


def _resolve_ref_audio(ref_audio_path: str) -> str:
    """Resolve ref_audio_path: if relative, try GSVI dir first, then AI dir.
    Returns absolute path or original if resolution fails."""
    if not ref_audio_path:
        return ""
    p = Path(ref_audio_path)
    if p.is_absolute():
        return str(p)
    # Try relative to GSVI directory
    candidate = _GSVI_DIR / p
    if candidate.exists():
        return str(candidate)
    # Try relative to AI dir
    candidate = _AI_DIR / p
    if candidate.exists():
        return str(candidate)
    # Fall back to original (may still work if GSVI can resolve it)
    return ref_audio_path


def synthesize(text: str, **kwargs: Any) -> bytes:
    """Call v2Pro /tts endpoint and return WAV bytes.

    kwargs may include:
        ref_audio_path: str   -- reference audio for voice cloning
        prompt_text: str      -- transcript of reference audio
        prompt_lang: str      -- language of reference audio
        text_lang: str        -- language of input text
        speed_factor: float   -- playback speed
        gpt_weights: str      -- T2S model path (relative to GSVI dir)
        sovits_weights: str   -- VITS model path (relative to GSVI dir)
    """
    base = _gsvi_url()
    text_lang_raw = kwargs.get("text_lang") or os.environ.get("GSVI_TEXT_LANG") or _infer_text_lang(text)
    prompt_lang_raw = kwargs.get("prompt_lang") or os.environ.get("GSVI_PROMPT_LANG") or "zh"
    ref_audio_path = kwargs.get("ref_audio_path") or os.environ.get("GSVI_REF_AUDIO") or ""
    prompt_text = kwargs.get("prompt_text") or os.environ.get("GSVI_PROMPT_TEXT") or ""
    speed = float(kwargs.get("speed_factor") or os.environ.get("GSVI_SPEED", "1.0"))
    gpt_weights = kwargs.get("gpt_weights") or os.environ.get("GSVI_GPT_WEIGHTS", "")
    sovits_weights = kwargs.get("sovits_weights") or os.environ.get("GSVI_SOVITS_WEIGHTS", "")

    # Resolve ref_audio to absolute path
    ref_audio_path = _resolve_ref_audio(ref_audio_path)

    # Switch to persona-specific model weights if available
    if gpt_weights or sovits_weights:
        _set_model_weights(gpt_weights, sovits_weights)

    payload: dict[str, Any] = {
        "text": text,
        "text_lang": _map_lang(text_lang_raw, _TEXT_LANG_MAP),
        "prompt_lang": _map_lang(prompt_lang_raw, _TEXT_LANG_MAP),
        "ref_audio_path": ref_audio_path,
        "speed_factor": speed,
        "streaming_mode": False,
    }
    if prompt_text:
        payload["prompt_text"] = prompt_text

    import time as _time
    _t0 = _time.time()
    full_url = f"{base}/tts"
    text_preview = text[:80].replace(chr(10), " ")
    print(f"[GSVI-v2pro] POST {full_url} text_lang={payload.get('text_lang')} prompt_lang={payload.get('prompt_lang')} speed={payload.get('speed_factor')}")
    print(f"[GSVI-v2pro] text='{text_preview}'")

    try:
        r = requests.post(
            full_url,
            json=payload,
            timeout=float(os.environ.get("GSVI_TIMEOUT", "300")),
        )
    except Exception as exc:
        print(f"[GSVI-v2pro] request error: {exc}")
        raise

    _elapsed = _time.time() - _t0
    if r.status_code == 200:
        print(f"[GSVI-v2pro] response 200 {len(r.content)} bytes in {_elapsed:.1f}s")
        return r.content
    else:
        # Log error details
        try:
            err_detail = r.json()
        except Exception:
            err_detail = r.text[:500]
        print(f"[GSVI-v2pro] response {r.status_code} in {_elapsed:.1f}s")
        print(f"[GSVI-v2pro] error detail: {err_detail}")
        r.raise_for_status()
        return r.content  # unreachable
