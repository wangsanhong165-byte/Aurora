"""Qwen3ASR engine — local 1.7B model. Config-driven."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import torch
from qwen_asr import Qwen3ASRModel

from app.modules.asr.base import BaseASR
from app.modules.asr.factory import ASRFactory

# Shared singleton (model is stateless, one per process)
_model: Qwen3ASRModel | None = None
_model_dir: Path | None = None


def _load(model_dir: Path) -> Qwen3ASRModel:
    global _model, _model_dir
    if _model is not None and _model_dir == model_dir:
        return _model

    if not model_dir.exists():
        raise RuntimeError(f"Model directory not found: {model_dir}")
    _model_dir = model_dir

    device_map = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32

    print(f"[ASR:qwen] Loading from {model_dir} (device={device_map}, dtype={dtype})")
    _model = Qwen3ASRModel.from_pretrained(
        str(model_dir),
        dtype=dtype,
        device_map=device_map,
        max_inference_batch_size=1,
        max_new_tokens=256,
    )
    print("[ASR:qwen] Model loaded")
    return _model


@ASRFactory.register
class QwenASR(BaseASR):
    engine_name = "qwen3-asr"

    def __init__(self, config: Any = None, **kwargs: Any) -> None:
        super().__init__()
        self._model_dir = Path(os.environ.get("ASR_MODEL_DIR", "./models/asr/Qwen3-ASR-1.7B"))
        if config is not None:
            from app.config_manager import QwenASRConfig
            if isinstance(config, QwenASRConfig) and config.model_dir:
                self._model_dir = Path(config.model_dir)

    def preload(self) -> None:
        """Load model weights onto the selected device without transcribing."""
        model_dir = self._model_dir or Path(".") / "models" / "asr" / "Qwen3-ASR-1.7B"
        _load(model_dir)

    def transcribe(self, audio_path: str, language: str | None = None) -> dict[str, Any]:
        model_dir = self._model_dir or Path(".") / "models" / "asr" / "Qwen3-ASR-1.7B"
        model = _load(model_dir)
        results = model.transcribe(audio=audio_path, language=language)
        r = results[0]
        return {"text": getattr(r, "text", ""), "language": getattr(r, "language", None)}
