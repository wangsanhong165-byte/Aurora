"""TTSFactory — create TTS engines by name."""

from __future__ import annotations

from typing import Any

from .base import BaseTTS


class TTSFactory:
    _engines: dict[str, type[BaseTTS]] = {}

    @classmethod
    def register(cls, engine_cls: type[BaseTTS]) -> type[BaseTTS]:
        cls._engines[engine_cls.engine_name] = engine_cls
        return engine_cls

    @classmethod
    def create(cls, engine_name: str | None = None, config: Any = None, **kwargs: Any) -> BaseTTS:
        from app.core.config import DEFAULT_TTS_ENGINE

        name = engine_name or DEFAULT_TTS_ENGINE
        if name not in cls._engines:
            raise ValueError(
                f"Unknown TTS engine: {name!r}. "
                f"Available: {list(cls._engines)}"
            )
        engine_cls = cls._engines[name]
        if config is not None:
            return engine_cls(config=config, **kwargs)
        return engine_cls(**kwargs)

    @classmethod
    def list_engines(cls) -> list[str]:
        return list(cls._engines.keys())
