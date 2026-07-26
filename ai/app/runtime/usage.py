"""LLM usage and configurable cost calculation."""

from __future__ import annotations

import os

from app.interfaces.llm import LLMUsage


def usage_report(usage: LLMUsage) -> dict:
    model = usage.model.lower()
    defaults = (
        (0.435, 0.003625, 0.87)
        if "v4-pro" in model else (0.14, 0.0028, 0.28)
    )
    miss_rate = float(os.getenv("LLM_INPUT_USD_PER_MILLION", str(defaults[0])))
    hit_rate = float(os.getenv("LLM_CACHED_INPUT_USD_PER_MILLION", str(defaults[1])))
    output_rate = float(os.getenv("LLM_OUTPUT_USD_PER_MILLION", str(defaults[2])))
    cached = min(usage.prompt_tokens, usage.cached_tokens)
    uncached = max(0, usage.prompt_tokens - cached)
    cost = (
        uncached * miss_rate + cached * hit_rate
        + usage.completion_tokens * output_rate
    ) / 1_000_000
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
        "cached_tokens": cached,
        "model": usage.model,
        "estimated": usage.estimated,
        "estimated_cost_usd": round(cost, 8),
    }
