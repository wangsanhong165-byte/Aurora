#!/usr/bin/env python
"""Stable one-click launcher for Web and Electron profiles."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parent.parent
LOCAL_CONFIG = ROOT / "config/runtime.local.json"
KNOWN_PYTHON = Path(r"C:\ProgramData\miniconda3\envs\qwen3-asr\python.exe")


@dataclass(frozen=True)
class LauncherConfig:
    root: Path
    python: Path


def choose_python(
    config_path: Path = LOCAL_CONFIG,
    environment: Mapping[str, str] | None = None,
) -> Path:
    env = environment if environment is not None else os.environ
    configured_env = env.get("MAIN_PYTHON")
    if configured_env and Path(configured_env).is_file():
        return Path(configured_env)
    if config_path.is_file():
        try:
            configured = Path(json.loads(config_path.read_text(encoding="utf-8"))["python"])
            if configured.is_file():
                return configured
        except (KeyError, OSError, ValueError, TypeError):
            pass
    if KNOWN_PYTHON.is_file():
        return KNOWN_PYTHON
    return Path(sys.executable)


def profile_command(config: LauncherConfig, profile: str) -> list[str]:
    if profile == "electron":
        npm = shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"
        return [npm, "run", "electron:start"]
    return [
        str(config.python),
        str(config.root / "scripts/lifecycle.py"),
        "start",
        "--mode",
        "backend",
    ]


def _run(command: list[str], *, cwd: Path, env: dict[str, str], dry_run: bool) -> None:
    print(f"[launcher] {' '.join(command)}")
    if dry_run:
        return
    subprocess.run(command, cwd=cwd, env=env, check=True)


def _doctor(config: LauncherConfig) -> list[str]:
    errors: list[str] = []
    if not config.python.is_file():
        errors.append(f"Python 不存在：{config.python}")
    else:
        probe = subprocess.run(
            [str(config.python), "-c", "import fastapi, psutil, requests, uvicorn"],
            cwd=config.root, capture_output=True, text=True,
        )
        if probe.returncode:
            errors.append(f"Python 环境缺少核心依赖：{probe.stderr.strip()}")
    if not shutil.which("node"):
        errors.append("找不到 Node.js")
    if not shutil.which("npm.cmd") and not shutil.which("npm"):
        errors.append("找不到 npm")
    required = [
        config.root / "config/services.json",
        config.root / "frontend/package.json",
        config.root / "models/tts/GPT-SoVITS-v2pro-20250604-nvidia50/runtime/python.exe",
    ]
    errors.extend(f"缺少文件：{path}" for path in required if not path.exists())
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Companion one-click launcher")
    parser.add_argument("profile", choices=["web", "electron", "doctor"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--pause-on-error", action="store_true")
    args = parser.parse_args()

    config = LauncherConfig(ROOT, choose_python())
    print(f"[launcher] Python: {config.python}")
    errors = _doctor(config)
    if args.profile == "doctor":
        if errors:
            print("\n".join(f"[FAIL] {error}" for error in errors))
            return 1
        print("[OK] 启动环境检查通过")
        return 0
    try:
        if errors:
            raise RuntimeError("\n".join(errors))
        env = os.environ.copy()
        env["MAIN_PYTHON"] = str(config.python)
        env.pop("ELECTRON_RUN_AS_NODE", None)
        if not args.skip_build:
            npm = shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"
            _run([npm, "run", "build"], cwd=ROOT / "frontend", env=env, dry_run=args.dry_run)
        if args.profile == "web":
            print("[launcher] Web 地址：http://127.0.0.1:9528")
        _run(
            profile_command(config, args.profile),
            cwd=ROOT / "frontend" if args.profile == "electron" else ROOT,
            env=env,
            dry_run=args.dry_run,
        )
        return 0
    except (OSError, subprocess.CalledProcessError, RuntimeError) as error:
        log_dir = ROOT / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "launcher-error.log").write_text(
            traceback.format_exc(), encoding="utf-8"
        )
        print(f"\n[启动失败] {error}", file=sys.stderr)
        print(f"[诊断] {config.python} {Path(__file__)} doctor", file=sys.stderr)
        print(f"[日志] {log_dir / 'launcher-error.log'}", file=sys.stderr)
        if args.pause_on_error:
            try:
                input("按 Enter 键关闭窗口……")
            except EOFError:
                pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
