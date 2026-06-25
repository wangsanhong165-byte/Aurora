"""Voice Agent configuration management — YAML + Pydantic.

Usage:
    from app.config_manager import load_config, AppConfig

    cfg = load_config("conf.yaml")
    print(cfg.tts.engine)  # "gsvi-v2pro"
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .main import AppConfig
from .system import SystemConfig
from .asr import ASRConfig, QwenASRConfig, CloudASRConfig
from .tts import TTSConfig, GSVIV2Config, QwenTTSConfig, EdgeTTSConfig, Pyttsx3Config, CloudTTSConfig
from .llm import LLMConfig, DeepSeekConfig, OpenAIConfig, OllamaConfig
from .memory import MemoryConfig, SQLiteMemoryConfig
from .i18n import I18nMixin, Description
from .utils import read_yaml, validate_config

# Convenience alias
load_config = read_yaml


def load_and_validate(path: str | Path = "conf.yaml") -> AppConfig:
    """Read YAML and validate against AppConfig."""
    data = read_yaml(path)
    return validate_config(AppConfig, data)


__all__ = [
    "AppConfig", "SystemConfig",
    "ASRConfig", "QwenASRConfig", "CloudASRConfig",
    "TTSConfig", "GSVIV2Config", "QwenTTSConfig", "EdgeTTSConfig", "Pyttsx3Config", "CloudTTSConfig",
    "LLMConfig", "DeepSeekConfig", "OpenAIConfig", "OllamaConfig",
    "MemoryConfig", "SQLiteMemoryConfig",
    "I18nMixin", "Description",
    "load_config", "load_and_validate", "read_yaml", "validate_config",
]
