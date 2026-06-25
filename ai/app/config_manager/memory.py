"""Memory configuration."""

from __future__ import annotations

from typing import Dict, ClassVar, Literal
from pydantic import Field
from .i18n import I18nMixin, Description


class SQLiteMemoryConfig(I18nMixin):
    """SQLite + FTS5 memory backend."""

    path: str = Field("./memory/memory.db", alias="path")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "path": Description(en="SQLite database path", zh="SQLite 数据库路径"),
    }


class MemoryConfig(I18nMixin):
    """Root memory configuration."""

    type: Literal["sqlite"] = "sqlite"
    sqlite: SQLiteMemoryConfig = Field(default_factory=SQLiteMemoryConfig, alias="sqlite")
