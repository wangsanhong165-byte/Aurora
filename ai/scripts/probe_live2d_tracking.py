"""Exercise hierarchical mouse tracking against the running Live2D page.

This is a motion-quality probe, not an FPS benchmark. It drives a real mouse
across the canvas and reads the same 4 Hz runtime snapshots shown by the Live2D
monitor, checking acquisition, torso lag, reversal inertia, and recovery.
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
    "ParamEyeBallX": 2.0,
    "ParamEyeBallY": 2.0,
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
    )
    return next((str(path) for path in candidates if path.exists()), None)


def snapshot(page: Any) -> dict[str, Any] | None:
    return page.evaluate(
        """() => {
          const value = globalThis.__SOULLINK_RUNTIME_SNAPSHOT__;
          if (!value) return null;
          return {
            observedAt: performance.now(),
            values: value.resolvedParameters || {},
            tracking: value.tracking || {},
          };
        }"""
    )


def collect(page: Any, duration: float) -> list[dict[str, Any]]:
    deadline = time.monotonic() + duration
    samples: list[dict[str, Any]] = []
    last_observed = -1.0
    while time.monotonic() < deadline:
        current = snapshot(page)
        observed = float(current.get("observedAt", -1)) if current else -1
        if current and observed != last_observed:
            samples.append(current)
            last_observed = observed
        page.wait_for_timeout(20)
    return samples


def number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else 0.0


def pose(sample: dict[str, Any], key: str) -> float:
    tracking = sample.get("tracking") or {}
    return number((tracking.get("pose") or {}).get(key))


def target(sample: dict[str, Any], axis: str) -> float:
    tracking = sample.get("tracking") or {}
    return number((tracking.get("target") or {}).get(axis))


def main() -> int:
    args = parse_args()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=not args.headed,
            executable_path=resolve_browser_executable(args.browser_executable),
        )
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(args.url, wait_until="networkidle")
        canvas = page.wait_for_selector("canvas", timeout=20_000)
        page.wait_for_function("() => Boolean(globalThis.__SOULLINK_RUNTIME_SNAPSHOT__)")
        correct_model = "Design_genius_White" in page.locator("body").inner_text()
        box = canvas.bounding_box()
        if not box:
            raise RuntimeError("Live2D canvas has no bounding box")

        def move(rx: float, ry: float) -> None:
            page.mouse.move(box["x"] + box["width"] * rx, box["y"] + box["height"] * ry)

        move(0.5, 0.5)
        center_before = collect(page, 0.7)
        move(0.88, 0.38)
        right = collect(page, 1.0)
        move(0.12, 0.62)
        left = collect(page, 1.0)
        move(0.5, 0.5)
        recovered = collect(page, 1.5)
        browser.close()

    all_samples = [*center_before, *right, *left, *recovered]
    max_step: dict[str, float] = {}
    for previous, current in zip(all_samples, all_samples[1:]):
        for parameter, full_range in PARAMETER_RANGES.items():
            before = number((previous.get("values") or {}).get(parameter))
            after = number((current.get("values") or {}).get(parameter))
            max_step[parameter] = max(max_step.get(parameter, 0), abs(after - before) / full_range)

    right_last = right[-1]
    left_first = next((sample for sample in left if target(sample, "x") < -0.5), left[0])
    left_last = left[-1]
    recovered_last = recovered[-1]
    result = {
        "sampleCounts": {
            "center": len(center_before), "right": len(right),
            "left": len(left), "recovered": len(recovered),
        },
        "right": {
            "targetX": target(right_last, "x"),
            "eyeX": pose(right_last, "eye.x"),
            "headX": pose(right_last, "head.x"),
            "bodyX": pose(right_last, "body.x"),
        },
        "reversalFirst": {
            "targetX": target(left_first, "x"),
            "eyeX": pose(left_first, "eye.x"),
            "headX": pose(left_first, "head.x"),
            "bodyX": pose(left_first, "body.x"),
        },
        "left": {
            "targetX": target(left_last, "x"),
            "eyeX": pose(left_last, "eye.x"),
            "headX": pose(left_last, "head.x"),
            "bodyX": pose(left_last, "body.x"),
        },
        "recovered": {
            "targetX": target(recovered_last, "x"),
            "eyeX": pose(recovered_last, "eye.x"),
            "headX": pose(recovered_last, "head.x"),
            "bodyX": pose(recovered_last, "body.x"),
        },
        "maxNormalizedStep": {key: round(value, 5) for key, value in max_step.items()},
    }
    checks = {
        "correctBenchmarkModel": correct_model,
        "rightTargetAcquired": result["right"]["targetX"] > 0.5,
        "rightHierarchyMoved": result["right"]["eyeX"] > 0.35
        and result["right"]["headX"] > 3 and result["right"]["bodyX"] > 0.3,
        "leftTargetAcquired": result["left"]["targetX"] < -0.5,
        "leftHierarchyMoved": result["left"]["eyeX"] < -0.35
        and result["left"]["headX"] < -3 and result["left"]["bodyX"] < -0.3,
        "reversalHasLayering": result["reversalFirst"]["eyeX"] < result["reversalFirst"]["bodyX"],
        "centerRecovered": abs(result["recovered"]["targetX"]) < 0.05
        and abs(result["recovered"]["eyeX"]) < 0.08
        and abs(result["recovered"]["headX"]) < 0.4
        and abs(result["recovered"]["bodyX"]) < 0.25,
        # Fast eyes are expected to cross a large commanded step within one
        # 4 Hz monitor sample. The physical torso channels must remain bounded.
        "physicalChannelsBounded": max(
            result["maxNormalizedStep"].get("ParamBodyAngleX", 0),
            result["maxNormalizedStep"].get("ParamBodyAngleY", 0),
            result["maxNormalizedStep"].get("ParamBodyAngleZ", 0),
        ) < 0.28,
    }
    result["checks"] = checks
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
