"""Root configuration — aggregates all module configs."""

from __future__ import annotations

from typing import Dict, ClassVar
from pydantic import Field
from .i18n import I18nMixin, Description
from .system import SystemConfig
from .asr import ASRConfig
from .tts import TTSConfig
from .llm import LLMConfig
from .memory import MemoryConfig


class AppConfig(I18nMixin):
    """Top-level application configuration."""

    system: SystemConfig = Field(default_factory=SystemConfig, alias="system")
    asr: ASRConfig = Field(default_factory=ASRConfig, alias="asr")
    tts: TTSConfig = Field(default_factory=TTSConfig, alias="tts")
    llm: LLMConfig = Field(default_factory=LLMConfig, alias="llm")
    memory: MemoryConfig = Field(default_factory=MemoryConfig, alias="memory")
    active_character: str = Field("monika", alias="active_character")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "active_character": Description(en="Active character ID", zh="当前角色 ID"),
    }
