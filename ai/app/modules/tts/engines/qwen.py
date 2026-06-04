"""Qwen3TTS engine — local 1.7B model with voice cloning."""
from __future__ import annotations

import io
import os
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

# ── Singleton ───────────────────────────────────────────────────
_model: Any = None
_MODELS_ROOT = Path(__file__).resolve().parents[4] / "models" / "tts"
_MODEL_DIR = Path(os.environ.get("TTS_MODEL_DIR", str(_MODELS_ROOT / "Qwen3-TTS-12Hz-0.6B-Base")))
_voice_clone_prompt = None


def load() -> Any:
    global _model, _voice_clone_prompt
    if _model is not None:
        return _model

    os.environ.setdefault("NUMBA_CACHE_DIR", os.path.join(os.environ.get("TEMP", "/tmp"), "numba_cache"))
    import torch
    from qwen_tts import Qwen3TTSModel

    if not _MODEL_DIR.exists():
        raise RuntimeError(f"Qwen3TTS model not found: {_MODEL_DIR}")

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if device.startswith("cuda") else torch.float32

    print(f"[TTS:qwen] Loading from {_MODEL_DIR} (device={device}, dtype={dtype})")
    _model = Qwen3TTSModel.from_pretrained(str(_MODEL_DIR), device_map=device, dtype=dtype)
    print("[TTS:qwen] Model loaded")

    ref_audio = os.environ.get("TTS_REF_AUDIO", "")
    ref_text = os.environ.get("TTS_REF_TEXT", "")
    if ref_audio:
        try:
            _voice_clone_prompt = _model.create_voice_clone_prompt(
                ref_audio=ref_audio, ref_text=ref_text or None, x_vector_only_mode=True,
            )
            print(f"[TTS:qwen] Voice clone prompt cached ({ref_audio})")
        except Exception as exc:
            print(f"[TTS:qwen] Clone prompt failed: {exc}")
    return _model


def synthesize(text: str, speaker: str = "", language: str = "") -> bytes:
    model = load()
    lang = language or os.environ.get("TTS_LANGUAGE", "zh")
    lang_map = {"zh": "Chinese", "cn": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean"}
    lang_label = lang_map.get(lang.lower(), "Chinese")

    ref_audio = os.environ.get("TTS_REF_AUDIO", "")
    if not ref_audio:
        raise RuntimeError("TTS_REF_AUDIO not set")

    tid = threading.current_thread().ident
    t0 = time.time()
    if _voice_clone_prompt is not None:
        print(f"[TTS:qwen] tid={tid} start t={t0:.1f} text={text[:20]}...")
        result = model.generate_voice_clone(
            text=text, language=lang_label, voice_clone_prompt=_voice_clone_prompt,
            max_new_tokens=160, do_sample=False, non_streaming_mode=True,
        )
    else:
        result = model.generate_voice_clone(
            text=text, language=lang_label, ref_audio=ref_audio, ref_text=os.environ.get("TTS_REF_TEXT", ""),
            max_new_tokens=160, do_sample=False, non_streaming_mode=True,
        )
    t1 = time.time()
    print(f"[TTS:qwen] tid={tid} done t={t1:.1f} dur={t1-t0:.1f}s")

    wavs_list, sr = result
    wavs = np.asarray(wavs_list[0], dtype=np.float32)
    if wavs.ndim == 2:
        wavs = wavs.flatten()
    buf = io.BytesIO()
    sf.write(buf, wavs, sr, format="WAV")
    return buf.getvalue()



