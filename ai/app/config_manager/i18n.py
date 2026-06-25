"""I18nMixin -- adds multi-language field descriptions to Pydantic models.

Adapted from Open-LLM-VTuber's config_manager/i18n.py.
"""

from __future__ import annotations

from typing import Dict, ClassVar
from pydantic import BaseModel, Field, ConfigDict


class Description(BaseModel):
    """A description in multiple languages."""

    en: str = Field(..., description="English translation")
    zh: str = Field(..., description="Chinese translation")


class MultiLingualString(BaseModel):
    """A string with translations in multiple languages."""

    en: str = Field(..., description="English translation")
    zh: str = Field(..., description="Chinese translation")


class I18nMixin(BaseModel):
    """Mixin that adds multi-language field descriptions.

    Subclasses define a DESCRIPTIONS class variable mapping field names
    to Description objects.
    """

    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {}

    @classmethod
    def get_field_description(cls, field_name: str, lang: str = "zh") -> str:
        desc = cls.DESCRIPTIONS.get(field_name)
        if desc is None:
            return ""
        return getattr(desc, lang, desc.en)
