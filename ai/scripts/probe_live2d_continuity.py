"""Probe the running Live2D controller for periodic parameter discontinuities.

The frontend publishes a bounded runtime snapshot four times per second.  This
script samples that snapshot from a real Chromium page, reports normalized
parameter jumps, and exits non-zero when an idle pose discontinuity is found.
It deliberately measures motion continuity, not frame rate.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any

from playwright.sync_api import sync_playwright


TRACKED_RANGES = {
    "ParamBreath": 1.0,
    "ParamAngleX": 60.0,
    "ParamAngleY": 60.0,
    "ParamAngleZ": 60.0,
    "ParamBodyAngleX": 20.0,
    "ParamBodyAngleY": 20.0,
    "ParamBodyAngleZ": 20.0,
    "ParamEyeBallX": 2.0,
    "ParamEyeBallY": 2.0,
}


@dataclass(frozen=True)
class Sample:
    observed_at: float
    values: dict[str, float]
    motion: str
    channels: tuple[str, ...]
    contested: dict[str, tuple[str, ...]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5173/")
    parser.add_argument("--duration", type=float, default=24.0)
    parser.add_argument("--jump-threshold", type=float, default=0.28)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--browser-executable")
    return parser.parse_args()


def resolve_browser_executable(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    candidates = (
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    )
    return next((str(path) for path in candidates if path.exists()), None)


def read_sample(page: Any) -> Sample | None:
    payload = page.evaluate(
        """() => {
          const snapshot = globalThis.__SOULLINK_RUNTIME_SNAPSHOT__;
          if (!snapshot) return null;
          const motion = snapshot.motion || {};
          const active = Array.isArray(motion.activeRequests)
            ? motion.activeRequests.map(item => item.name || item.owner || '').filter(Boolean)
            : [];
          return {
            values: snapshot.resolvedParameters || {},
            motion: active.join(',') || motion.currentMotion || '',
            channels: snapshot.activeChannels || [],
            contested: snapshot.contestedParameters || {},
          };
        }"""
    )
    if not payload:
        return None
    values = {
        parameter: float(payload["values"][parameter])
        for parameter in TRACKED_RANGES
        if parameter in payload["values"]
        and isinstance(payload["values"][parameter], (int, float))
        and math.isfinite(payload["values"][parameter])
    }
    return Sample(
        observed_at=time.monotonic(),
        values=values,
        motion=str(payload.get("motion") or ""),
        channels=tuple(str(value) for value in payload.get("channels") or []),
        contested={
            str(parameter): tuple(
                str(item.get("source") or "")
                for item in values
                if isinstance(item, dict) and item.get("source")
            )
            for parameter, values in (payload.get("contested") or {}).items()
            if isinstance(values, list)
        },
    )


def main() -> int:
    args = parse_args()
    samples: list[Sample] = []
    jumps: list[dict[str, Any]] = []
    last_fingerprint = ""

    with sync_playwright() as playwright:
        executable = resolve_browser_executable(args.browser_executable)
        browser = playwright.chromium.launch(
            headless=not args.headed,
            executable_path=executable,
        )
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(args.url, wait_until="networkidle")
        page.wait_for_selector("canvas", timeout=20_000)
        deadline = time.monotonic() + max(2.0, args.duration)
        while time.monotonic() < deadline:
            sample = read_sample(page)
            if sample:
                fingerprint = json.dumps(
                    [sample.values, sample.motion, sample.channels, sample.contested],
                    sort_keys=True,
                    ensure_ascii=True,
                )
                if fingerprint != last_fingerprint:
                    if samples:
                        previous = samples[-1]
                        for parameter, value in sample.values.items():
                            if parameter not in previous.values:
                                continue
                            normalized_delta = abs(value - previous.values[parameter]) / TRACKED_RANGES[parameter]
                            if normalized_delta >= args.jump_threshold:
                                jumps.append(
                                    {
                                        "atSeconds": round(sample.observed_at - samples[0].observed_at, 3),
                                        "parameter": parameter,
                                        "from": round(previous.values[parameter], 5),
                                        "to": round(value, 5),
                                        "normalizedDelta": round(normalized_delta, 5),
                                        "beforeMotion": previous.motion,
                                        "afterMotion": sample.motion,
                                        "beforeChannels": previous.channels,
                                        "afterChannels": sample.channels,
                                    }
                                )
                    samples.append(sample)
                    last_fingerprint = fingerprint
            page.wait_for_timeout(50)
        browser.close()

    source_sets: Counter[str] = Counter()
    parameter_conflicts: Counter[str] = Counter()
    normalized_steps: dict[str, list[float]] = {key: [] for key in TRACKED_RANGES}
    for sample in samples:
        for parameter, sources in sample.contested.items():
            parameter_conflicts[parameter] += 1
            source_sets[" + ".join(sorted(set(sources)))] += 1
    for previous, current in zip(samples, samples[1:]):
        for parameter, value in current.values.items():
            if parameter in previous.values:
                normalized_steps[parameter].append(
                    abs(value - previous.values[parameter]) / TRACKED_RANGES[parameter]
                )

    result = {
        "sampleCount": len(samples),
        "durationSeconds": args.duration,
        "jumpThreshold": args.jump_threshold,
        "jumps": jumps,
        "conflictFrames": sum(bool(sample.contested) for sample in samples),
        "topConflictedParameters": parameter_conflicts.most_common(8),
        "topSourceCombinations": source_sets.most_common(8),
        "meanNormalizedStep": {
            parameter: round(sum(steps) / len(steps), 6)
            for parameter, steps in normalized_steps.items()
            if steps
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if jumps else 0


if __name__ == "__main__":
    raise SystemExit(main())
