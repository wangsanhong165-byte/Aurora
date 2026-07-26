"""Fail CI when Runtime replay metrics exceed declared thresholds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def evaluate_quality_gate(
    metrics: dict,
    *,
    max_p95_latency_ms: float,
    max_repeat_rate: float,
    min_persona_score: float,
) -> list[str]:
    failures = []
    if float(metrics.get("p95_latency_ms", 0)) > max_p95_latency_ms:
        failures.append("p95_latency_ms")
    if float(metrics.get("reply_exact_repeat_rate", 0)) > max_repeat_rate:
        failures.append("reply_exact_repeat_rate")
    if float(metrics.get("persona_score", 0)) < min_persona_score:
        failures.append("persona_score")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--max-p95-latency-ms", type=float, required=True)
    parser.add_argument("--max-repeat-rate", type=float, required=True)
    parser.add_argument("--min-persona-score", type=float, required=True)
    args = parser.parse_args()
    metrics = json.loads(Path(args.metrics).read_text("utf-8"))
    failures = evaluate_quality_gate(
        metrics,
        max_p95_latency_ms=args.max_p95_latency_ms,
        max_repeat_rate=args.max_repeat_rate,
        min_persona_score=args.min_persona_score,
    )
    if failures:
        print("quality gate failed: " + ", ".join(failures))
        return 1
    print("quality gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
