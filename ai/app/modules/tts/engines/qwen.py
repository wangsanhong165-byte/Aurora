"""Qwen3TTS engine — local model with voice cloning. Config-driven."""

from __future__ import annotations

import io
import os
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from app.modules.tts.base import BaseTTS
from app.modules.tts.factory import TTSFactory

# ---- Shared singleton (model is stateless, one per process) ----
_model: Any = None
_model_dir_loaded: str | None = None
_voice_clone_prompt = None


def _load(model_dir: Path, ref_audio: str, ref_text: str) -> Any:
    global _model, _model_dir_loaded, _voice_clone_prompt
    if _model is not None and _model_dir_loaded == str(model_dir):
        return _model

    os.environ.setdefault("NUMBA_CACHE_DIR", os.path.join(os.environ.get("TEMP", "/tmp"), "numba_cache"))
    import torch
    from qwen_tts import Qwen3TTSModel

    if not model_dir.exists():
        raise RuntimeError(f"Qwen3TTS model not found: {model_dir}")
    _model_dir_loaded = str(model_dir)

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if device.startswith("cuda") else torch.float32

    print(f"[TTS:qwen] Loading from {model_dir} (device={device}, dtype={dtype})")
    _model = Qwen3TTSModel.from_pretrained(str(model_dir), device_map=device, dtype=dtype)
    print("[TTS:qwen] Model loaded")

    _voice_clone_prompt = None
    if ref_audio:
        try:
            _voice_clone_prompt = _model.create_voice_clone_prompt(
                ref_audio=ref_audio, ref_text=ref_text or None, x_vector_only_mode=True,
            )
            print(f"[TTS:qwen] Voice clone prompt cached ({ref_audio})")
        except Exception as exc:
            print(f"[TTS:qwen] Clone prompt failed: {exc}")
    return _model


_LANG_MAP = {"zh": "Chinese", "cn": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean"}


@TTSFactory.register
class QwenTTS(BaseTTS):
    engine_name = "qwen3-tts"

    def __init__(self, config: Any = None, **kwargs: Any) -> None:
        super().__init__()
        _models_root = Path(__file__).resolve().parents[4] / "models" / "tts"
        _default_model = str(_models_root / "Qwen3-TTS-12Hz-0.6B-Base")
        # Priority: config > env var > hardcoded default
        self._model_dir = Path(os.environ.get("TTS_MODEL_DIR", _default_model))
        self._ref_audio = os.environ.get("TTS_REF_AUDIO", "")
        self._ref_text = os.environ.get("TTS_REF_TEXT", "")
        self._language = os.environ.get("TTS_LANGUAGE", "zh")
        if config is not None:
            from app.config_manager import QwenTTSConfig
            if isinstance(config, QwenTTSConfig):
                if config.model_dir:
                    self._model_dir = Path(config.model_dir)
                if config.ref_audio:
                    self._ref_audio = config.ref_audio
                if config.ref_text:
                    self._ref_text = config.ref_text
                if config.language:
                    self._language = config.language

    def synthesize(self, text: str, **options: Any) -> bytes:
        speaker = options.get("speaker", "")
        language = options.get("language", "") or self._language
        lang_label = _LANG_MAP.get(language.lower(), "Chinese")

        if not self._ref_audio:
            raise RuntimeError("TTS_REF_AUDIO not set (configure in conf.yaml or .env)")

        model = _load(self._model_dir, self._ref_audio, self._ref_text)
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
                text=text, language=lang_label, ref_audio=self._ref_audio,
                ref_text=self._ref_text,
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
