"""LLM configurations."""

from __future__ import annotations

from typing import Optional, Dict, ClassVar, Literal
from pydantic import Field
from .i18n import I18nMixin, Description


LLMEngineType = Literal["deepseek", "openai", "ollama", "claude"]


class DeepSeekConfig(I18nMixin):
    """DeepSeek API."""

    engine: Literal["deepseek"] = "deepseek"
    base_url: str = Field("https://api.deepseek.com", alias="base_url")
    model: str = Field("deepseek-chat", alias="model")
    api_key: str = Field("", alias="api_key")
    temperature: float = Field(0.3, alias="temperature")
    reasoning_effort: str = Field("medium", alias="reasoning_effort")
    timeout: int = Field(60, alias="timeout")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "base_url": Description(en="API base URL", zh="API 地址"),
        "model": Description(en="Model name", zh="模型名称"),
        "temperature": Description(en="Sampling temperature", zh="采样温度"),
    }


class OpenAIConfig(I18nMixin):
    """OpenAI-compatible API."""

    engine: Literal["openai"] = "openai"
    base_url: str = Field("https://api.openai.com/v1", alias="base_url")
    model: str = Field("gpt-4o", alias="model")
    api_key: str = Field("", alias="api_key")
    temperature: float = Field(0.3, alias="temperature")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "base_url": Description(en="API base URL", zh="API 地址"),
        "model": Description(en="Model name", zh="模型名称"),
    }


class OllamaConfig(I18nMixin):
    engine: Literal["ollama"] = "ollama"
    base_url: str = Field("http://127.0.0.1:11434", alias="base_url")
    model: str = Field("", alias="model")
    temperature: float = Field(0.3, alias="temperature")


class LLMConfig(I18nMixin):
    """Root LLM configuration."""

    engine: LLMEngineType = Field("deepseek", alias="engine")
    deepseek: DeepSeekConfig = Field(default_factory=DeepSeekConfig, alias="deepseek")
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig, alias="openai")
    ollama: OllamaConfig = Field(default_factory=OllamaConfig, alias="ollama")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "engine": Description(en="Active LLM engine", zh="当前 LLM 引擎"),
    }
