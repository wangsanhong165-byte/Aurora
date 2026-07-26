"""Deterministic hybrid scoring for local memory retrieval."""

from __future__ import annotations

import math
import re
import time
from difflib import SequenceMatcher
from typing import Any

_ALIASES = {
    "bug": "程序错误",
    "报错": "程序错误",
    "错误": "程序错误",
    "爱吃": "喜欢",
    "爱好": "喜欢",
    "喜好": "喜欢",
    "烦": "烦躁",
    "记得": "记忆",
}


def normalize(text: str) -> str:
    value = str(text or "").lower()
    for source, target in _ALIASES.items():
        value = value.replace(source, target)
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE)


def _ngrams(value: str, size: int = 2) -> set[str]:
    if len(value) < size:
        return {value} if value else set()
    return {value[i:i + size] for i in range(len(value) - size + 1)}


def score_memory(query: str, item: dict[str, Any], now: float | None = None) -> tuple[float, list[str]]:
    q = normalize(query)
    content = normalize(item.get("content") or item.get("fact") or "")
    if not q or not content:
        return 0.0, []

    reasons: list[str] = []
    qgrams, cgrams = _ngrams(q), _ngrams(content)
    overlap = len(qgrams & cgrams) / max(1, len(qgrams))
    sequence = SequenceMatcher(None, q, content).ratio()
    if q in content or content in q:
        lexical = 1.0
        reasons.append("direct_match")
    else:
        lexical = max(overlap, sequence * 0.65)
        if overlap:
            reasons.append("semantic_overlap")

    importance = max(0.0, min(1.0, float(item.get("importance", 0.5) or 0.5)))
    confidence = max(0.0, min(1.0, float(item.get("confidence", 0.6) or 0.6)))
    created = float(item.get("updated_ts", item.get("created_ts", 0.0)) or 0.0)
    age_days = max(0.0, ((now or time.time()) - created) / 86400) if created else 30.0
    recency = math.exp(-age_days / 180.0)
    score = lexical * 0.68 + importance * 0.14 + confidence * 0.12 + recency * 0.06
    if importance >= 0.75:
        reasons.append("important")
    if recency >= 0.8:
        reasons.append("recent")
    return score, reasons
