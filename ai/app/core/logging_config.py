"""Centralised logging configuration for the Companion Runtime.

Usage:
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("Service started", extra={"port": 9103})

Features:
    - TimedRotatingFileHandler — daily rotation, 30-day retention
    - JSON-structured output (timestamp, level, logger, message, correlation_id)
    - Correlation ID for end-to-end request tracing
    - Console fallback for interactive use (py.exe run.py)
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
import time
import uuid
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

# ── Correlation ID (context-local per-request) ─────────────────────────
_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)

LOG_DIR = Path(os.environ.get("LOG_DIR", Path(__file__).resolve().parents[2] / "logs"))


def set_correlation_id(cid: str | None = None) -> str:
    """Set a correlation ID for the current context. Returns the ID."""
    cid = cid or uuid.uuid4().hex[:12]
    _correlation_id.set(cid)
    return cid


def get_correlation_id() -> str:
    return _correlation_id.get()


# ── JSON formatter ──────────────────────────────────────────────────────


class JsonFormatter(logging.Formatter):
    """Emit log records as JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.") + f"{int(record.msecs):03d}",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        cid = get_correlation_id()
        if cid:
            payload["cid"] = cid
        if record.exc_info and record.exc_info[1]:
            payload["exc"] = str(record.exc_info[1])
        # Merge extra fields
        for key in ("port", "service", "pid", "elapsed", "status"):
            val = getattr(record, key, None)
            if val is not None:
                payload[key] = val
        return json.dumps(payload, ensure_ascii=False, default=str)


# ── Factory ─────────────────────────────────────────────────────────────

_initialised = False


def _init_root_logger() -> None:
    """Configure root logger once with file + console handlers."""
    global _initialised
    if _initialised:
        return
    _initialised = True

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # File handler — daily rotation, 30-day retention
    fh = TimedRotatingFileHandler(
        str(LOG_DIR / "companion.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(JsonFormatter())
    root.addHandler(fh)

    # Console handler — human-readable for interactive use
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(os.environ.get("LOG_LEVEL_CONSOLE", "INFO").upper())
    ch.setFormatter(
        logging.Formatter(
            "[%(name)s] %(asctime)s %(levelname)-5s %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root.addHandler(ch)


def get_logger(name: str) -> logging.Logger:
    """Return a logger with the project-wide configuration applied.

    Call once per module (usually at module level).
    """
    _init_root_logger()
    return logging.getLogger(name)


# ── Service-log helper ──────────────────────────────────────────────────


def service_log_path(service_name: str) -> Path:
    """Return the path for a per-service log file."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR / f"{service_name}.log"
