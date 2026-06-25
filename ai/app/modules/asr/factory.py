"""ASRFactory — create ASR engines by name."""

from __future__ import annotations

from typing import Any, Optional

from .base import BaseASR


class ASRFactory:
    _engines: dict[str, type[BaseASR]] = {}

    @classmethod
    def register(cls, engine_cls: type[BaseASR]) -> type[BaseASR]:
        cls._engines[engine_cls.engine_name] = engine_cls
        return engine_cls

    @classmethod
    def create(cls, engine_name: str | None = None, config: Any = None, **kwargs: Any) -> BaseASR:
        from app.core.config import DEFAULT_ASR_ENGINE

        name = engine_name or DEFAULT_ASR_ENGINE
        if name not in cls._engines:
            raise ValueError(
                f"Unknown ASR engine: {name!r}. "
                f"Available: {list(cls._engines)}"
            )
        engine_cls = cls._engines[name]
        # Pass config if engine accepts it
        if config is not None:
            return engine_cls(config=config, **kwargs)
        return engine_cls(**kwargs)

    @classmethod
    def list_engines(cls) -> list[str]:
        return list(cls._engines.keys())
