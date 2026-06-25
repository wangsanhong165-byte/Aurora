"""ASR engine configurations."""

from __future__ import annotations

from typing import Optional, Dict, ClassVar, Literal
from pydantic import Field
from .i18n import I18nMixin, Description


ASREngineType = Literal["qwen3-asr", "cloud-asr"]


class QwenASRConfig(I18nMixin):
    """Local Qwen3-ASR engine."""

    engine: Literal["qwen3-asr"] = "qwen3-asr"
    model_dir: str = Field("./models/asr/Qwen3-ASR-1.7B", alias="model_dir")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "model_dir": Description(en="Path to Qwen3-ASR model", zh="Qwen3-ASR 模型路径"),
    }


class CloudASRConfig(I18nMixin):
    """Cloud ASR via API."""

    engine: Literal["cloud-asr"] = "cloud-asr"
    base_url: str = Field("", alias="base_url")
    api_key: str = Field("", alias="api_key")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "base_url": Description(en="ASR API base URL", zh="ASR API 地址"),
        "api_key": Description(en="ASR API key (use env var)", zh="ASR API 密钥（使用环境变量）"),
    }


class ASRConfig(I18nMixin):
    """Root ASR configuration."""

    engine: ASREngineType = Field("qwen3-asr", alias="engine")
    qwen3_asr: QwenASRConfig = Field(default_factory=QwenASRConfig, alias="qwen3-asr")
    cloud_asr: CloudASRConfig = Field(default_factory=CloudASRConfig, alias="cloud-asr")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "engine": Description(en="Active ASR engine name", zh="当前 ASR 引擎"),
    }
