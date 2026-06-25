"""System-level configuration."""

from __future__ import annotations

from typing import Dict, ClassVar
from pydantic import Field
from .i18n import I18nMixin, Description


class SystemConfig(I18nMixin):
    """System-wide settings."""

    base_dir: str = Field(".", alias="base_dir")
    models_dir: str = Field("./models", alias="models_dir")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "base_dir": Description(en="Project base directory", zh="项目根目录"),
        "models_dir": Description(en="Models root directory", zh="模型根目录"),
    }
