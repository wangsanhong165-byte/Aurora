
"""Utility functions: read YAML, validate config, env-var substitution."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, TypeVar

import yaml
from pydantic import BaseModel, ValidationError


T = TypeVar("T", bound=BaseModel)

_ENV_PATTERN = re.compile(r"\$(\w+)(?::-(\w+))?")


def read_yaml(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    content = _load_text(path)
    if not content:
        raise IOError(f"Failed to read: {path}")
    def _replacer(m):
        return os.environ.get(m.group(1), m.group(2) or "")
    content = _ENV_PATTERN.sub(_replacer, content)
    try:
        return yaml.safe_load(content) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"YAML parse error in {path}: {e}") from e


def validate_config(model_cls, data):
    try:
        return model_cls(**data)
    except ValidationError as e:
        raise ValueError(f"Config validation failed: {e}") from e


def _load_text(path):
    encodings = ["utf-8", "utf-8-sig", "gbk", "gb2312", "ascii", "cp936"]
    for enc in encodings:
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    try:
        return path.read_bytes().decode("latin-1")
    except Exception:
        return None
