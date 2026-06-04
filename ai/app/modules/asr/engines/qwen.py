"""Qwen3ASR engine — local 1.7B model."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import torch
from qwen_asr import Qwen3ASRModel

from app.core.config import DEFAULT_MODEL_DIR

_model: Qwen3ASRModel | None = None
_model_dir: Path = DEFAULT_MODEL_DIR


def set_model_dir(path: Path) -> None:
    global _model_dir
    _model_dir = path


def load() -> Qwen3ASRModel:
    global _model
    if _model is not None:
        return _model

    if not _model_dir.exists():
        raise RuntimeError(f"Model directory not found: {_model_dir}")

    device_map = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32

    print(f"[ASR:qwen] Loading from {_model_dir} (device={device_map}, dtype={dtype})")
    _model = Qwen3ASRModel.from_pretrained(
        str(_model_dir),
        dtype=dtype,
        device_map=device_map,
        max_inference_batch_size=1,
        max_new_tokens=256,
    )
    print("[ASR:qwen] Model loaded")
    return _model


def transcribe(audio_path: str, language: str | None = None) -> dict[str, Any]:
    model = load()
    results = model.transcribe(audio=audio_path, language=language)
    r = results[0]
    return {"text": getattr(r, "text", ""), "language": getattr(r, "language", None)}
