"""Compare Runtime replay metrics with a recorded baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    baseline = json.loads(Path(args.baseline).read_text("utf-8"))
    candidate = json.loads(Path(args.candidate).read_text("utf-8"))
    keys = sorted(set(baseline) | set(candidate))
    rows = ["# Runtime replay comparison", "", "| Metric | Baseline | Candidate | Delta |", "|---|---:|---:|---:|"]
    for key in keys:
        before = float(baseline.get(key, 0))
        after = float(candidate.get(key, 0))
        rows.append(f"| {key} | {before:.4f} | {after:.4f} | {after - before:+.4f} |")
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
