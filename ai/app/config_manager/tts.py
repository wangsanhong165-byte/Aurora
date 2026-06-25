"""TTS engine configurations."""

from __future__ import annotations

from typing import Optional, Dict, ClassVar, Literal
from pydantic import Field
from .i18n import I18nMixin, Description


TTSEngineType = Literal["gsvi-v2pro", "qwen3-tts", "edge-tts", "pyttsx3", "cloud-tts"]


class GSVIV2Config(I18nMixin):
    """GPT-SoVITS v2Pro engine (nvidia50)."""

    engine: Literal["gsvi-v2pro"] = "gsvi-v2pro"
    url: str = Field("http://127.0.0.1:8050", alias="url")
    ref_audio: str = Field("", alias="ref_audio")
    prompt_text: str = Field("", alias="prompt_text")
    text_lang: str = Field("zh", alias="text_lang")
    prompt_lang: str = Field("zh", alias="prompt_lang")
    speed: float = Field(1.0, alias="speed")
    timeout: int = Field(300, alias="timeout")
    gpt_weights: str = Field("", alias="gpt_weights")
    sovits_weights: str = Field("", alias="sovits_weights")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "url": Description(en="GSVI API URL", zh="GSVI API 地址"),
        "ref_audio": Description(en="Reference audio path for voice cloning", zh="参考音频路径"),
        "text_lang": Description(en="Input text language (zh/en/ja/ko/yue)", zh="输入文本语言"),
        "speed": Description(en="Speech speed factor", zh="语速系数"),
    }


class QwenTTSConfig(I18nMixin):
    """Local Qwen3-TTS engine."""

    engine: Literal["qwen3-tts"] = "qwen3-tts"
    model_dir: str = Field("./models/tts/Qwen3-TTS-12Hz-0.6B-Base", alias="model_dir")
    ref_audio: str = Field("", alias="ref_audio")
    ref_text: str = Field("", alias="ref_text")
    language: str = Field("zh", alias="language")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "model_dir": Description(en="Path to Qwen3-TTS model", zh="Qwen3-TTS 模型路径"),
        "ref_audio": Description(en="Reference audio for voice cloning", zh="语音克隆参考音频"),
        "language": Description(en="Output language", zh="输出语言"),
    }


class EdgeTTSConfig(I18nMixin):
    """Microsoft Edge TTS (free, no GPU)."""

    engine: Literal["edge-tts"] = "edge-tts"
    voice: str = Field("zh-CN-XiaoxiaoNeural", alias="voice")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "voice": Description(en="Edge TTS voice name", zh="Edge TTS 语音名称"),
    }


class Pyttsx3Config(I18nMixin):
    """System fallback TTS."""

    engine: Literal["pyttsx3"] = "pyttsx3"


class CloudTTSConfig(I18nMixin):
    """External cloud TTS API."""

    engine: Literal["cloud-tts"] = "cloud-tts"
    base_url: str = Field("", alias="base_url")
    api_key: str = Field("", alias="api_key")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "base_url": Description(en="TTS API base URL", zh="TTS API 地址"),
        "api_key": Description(en="TTS API key (use env var)", zh="TTS API 密钥"),
    }


class TTSConfig(I18nMixin):
    """Root TTS configuration."""

    engine: TTSEngineType = Field("gsvi-v2pro", alias="engine")
    output_dir: str = Field("./tts_outputs", alias="output_dir")
    gsvi_v2pro: GSVIV2Config = Field(default_factory=GSVIV2Config, alias="gsvi-v2pro")
    qwen3_tts: QwenTTSConfig = Field(default_factory=QwenTTSConfig, alias="qwen3-tts")
    edge_tts: EdgeTTSConfig = Field(default_factory=EdgeTTSConfig, alias="edge-tts")
    pyttsx3: Pyttsx3Config = Field(default_factory=Pyttsx3Config, alias="pyttsx3")
    cloud_tts: CloudTTSConfig = Field(default_factory=CloudTTSConfig, alias="cloud-tts")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "engine": Description(en="Active TTS engine name", zh="当前 TTS 引擎"),
        "output_dir": Description(en="TTS audio output directory", zh="TTS 音频输出目录"),
    }
