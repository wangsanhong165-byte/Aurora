"""Validate pointer tracking and ambient motion coordination in a real page.

This is a behavioral continuity probe, not an FPS benchmark. It holds the
pointer over the avatar long enough for the autonomous-attention scheduler to
want to run, then verifies that pointer engagement keeps ownership without
freezing compatible torso motion or snapping on release.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import time
from typing import Any

from playwright.sync_api import sync_playwright


PARAMETER_RANGES = {
    "ParamAngleX": 60.0,
    "ParamAngleY": 60.0,
    "ParamAngleZ": 60.0,
    "ParamBodyAngleX": 20.0,
    "ParamBodyAngleY": 20.0,
    "ParamBodyAngleZ": 20.0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5173/")
    parser.add_argument("--hold-seconds", type=float, default=15.0)
    parser.add_argument("--release-seconds", type=float, default=3.0)
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


def read_snapshot(page: Any) -> dict[str, Any] | None:
    return page.evaluate(
        """() => {
          const value = globalThis.__SOULLINK_RUNTIME_SNAPSHOT__;
          if (!value) return null;
          return {
            model: value.model || '',
            at: performance.now(),
            values: value.resolvedParameters || {},
            tracking: value.tracking || {},
            attention: value.attention || {},
            idle: value.idle || {},
          };
        }"""
    )


def collect(page: Any, seconds: float) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    deadline = time.monotonic() + max(0.5, seconds)
    last_fingerprint = ""
    while time.monotonic() < deadline:
        sample = read_snapshot(page)
        fingerprint = json.dumps(
            {
                "values": (sample or {}).get("values") or {},
                "tracking": (sample or {}).get("tracking") or {},
                "attention": (sample or {}).get("attention") or {},
                "idle": (sample or {}).get("idle") or {},
            },
            sort_keys=True,
            ensure_ascii=True,
        )
        if sample and fingerprint != last_fingerprint:
            samples.append(sample)
            last_fingerprint = fingerprint
        page.wait_for_timeout(40)
    return samples


def finite_values(samples: list[dict[str, Any]], parameter: str) -> list[float]:
    result: list[float] = []
    for sample in samples:
        value = (sample.get("values") or {}).get(parameter)
        if isinstance(value, (int, float)) and math.isfinite(value):
            result.append(float(value))
    return result


def max_normalized_step(samples: list[dict[str, Any]], parameters: tuple[str, ...]) -> float:
    result = 0.0
    for previous, current in zip(samples, samples[1:]):
        for parameter in parameters:
            before = (previous.get("values") or {}).get(parameter)
            after = (current.get("values") or {}).get(parameter)
            if isinstance(before, (int, float)) and isinstance(after, (int, float)):
                result = max(result, abs(float(after) - float(before)) / PARAMETER_RANGES[parameter])
    return result


def autonomous_episode(sample: dict[str, Any] | None) -> int:
    attention = (sample or {}).get("attention") or {}
    autonomous = attention.get("autonomous") or {}
    value = autonomous.get("episode") or autonomous.get("episodeId") or 0
    return int(value) if isinstance(value, (int, float)) else 0


def engagement(sample: dict[str, Any] | None) -> float:
    tracking = (sample or {}).get("tracking") or {}
    state = tracking.get("engagement") or {}
    value = state.get("weight") or 0.0
    return float(value) if isinstance(value, (int, float)) else 0.0


def main() -> int:
    args = parse_args()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=not args.headed,
            executable_path=resolve_browser_executable(args.browser_executable),
        )
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(args.url, wait_until="networkidle")
        canvas = page.locator("canvas").first
        canvas.wait_for(timeout=20_000)
        page.wait_for_function("() => Boolean(globalThis.__SOULLINK_RUNTIME_SNAPSHOT__)")
        box = canvas.bounding_box()
        if not box:
            raise RuntimeError("Live2D canvas has no bounding box")

        page.mouse.move(box["x"] + box["width"] * 0.82, box["y"] + box["height"] * 0.38)
        held = collect(page, args.hold_seconds)

        # Leave through the stage edge so the real mouseleave/release path runs.
        page.mouse.move(2, 2)
        released = collect(page, args.release_seconds)
        browser.close()

    held_after_acquire = held[4:] if len(held) > 4 else held
    body_values = [
        value
        for parameter in ("ParamBodyAngleX", "ParamBodyAngleY", "ParamBodyAngleZ")
        for value in finite_values(held_after_acquire, parameter)
    ]
    torso_span = (max(body_values) - min(body_values)) if body_values else 0.0
    held_episodes = [autonomous_episode(sample) for sample in held]
    release_episodes = [autonomous_episode(sample) for sample in released]
    held_engagement = [engagement(sample) for sample in held]
    release_engagement = [engagement(sample) for sample in released]
    model = str((held[0] if held else {}).get("model") or "")

    metrics = {
        "model": model,
        "heldSampleCount": len(held),
        "releasedSampleCount": len(released),
        "maximumHeldEngagement": round(max(held_engagement, default=0.0), 5),
        "finalReleaseEngagement": round(release_engagement[-1] if release_engagement else 1.0, 5),
        "heldAutonomousEpisodeDelta": max(held_episodes, default=0) - min(held_episodes, default=0),
        "releaseAutonomousEpisodeDelta": max(release_episodes, default=0) - min(release_episodes, default=0),
        "torsoSpanDuringHold": round(torso_span, 5),
        "heldHeadMaxNormalizedStep": round(
            max_normalized_step(held_after_acquire, ("ParamAngleX", "ParamAngleY", "ParamAngleZ")), 5
        ),
        "releaseHeadMaxNormalizedStep": round(
            max_normalized_step(released, ("ParamAngleX", "ParamAngleY", "ParamAngleZ")), 5
        ),
    }
    checks = {
        "correctBenchmarkModel": model == "Design_genius_White",
        "pointerEngagementAcquired": metrics["maximumHeldEngagement"] >= 0.9,
        "autonomousAttentionSuspendedDuringHold": metrics["heldAutonomousEpisodeDelta"] == 0,
        "compatibleTorsoLifePreserved": metrics["torsoSpanDuringHold"] >= 0.04,
        "heldTrackingContinuous": metrics["heldHeadMaxNormalizedStep"] < 0.08,
        "releaseTrackingContinuous": metrics["releaseHeadMaxNormalizedStep"] < 0.12,
        "pointerEngagementReleased": metrics["finalReleaseEngagement"] <= 0.12,
        "autonomousCooldownPreserved": metrics["releaseAutonomousEpisodeDelta"] == 0,
    }
    result = {"metrics": metrics, "checks": checks, "ok": all(checks.values())}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
