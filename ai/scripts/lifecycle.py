#!/usr/bin/env python
"""Thin CLI for the canonical Python lifecycle core."""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.lifecycle import LifecycleOrchestrator, ServiceManifest


def create_orchestrator(args=None) -> LifecycleOrchestrator:
    user_overrides = {}
    if args and getattr(args, "config", None):
        user_overrides = json.loads(Path(args.config).read_text(encoding="utf-8"))
    cli_overrides = {}
    for item in getattr(args, "port", []) if args else []:
        name, value = item.split("=", 1)
        cli_overrides.setdefault(name, {})["port"] = int(value)
    return LifecycleOrchestrator(
        ROOT, ServiceManifest.load(
            ROOT / "config/services.json",
            overrides=user_overrides,
            cli_overrides=cli_overrides,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Companion lifecycle manager")
    parser.add_argument("--config", help="JSON user override file")
    parser.add_argument("--port", action="append", default=[], metavar="SERVICE=PORT")
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start")
    start.add_argument("--mode", choices=["backend", "web", "full", "electron"], default="full")
    sub.add_parser("stop")
    restart = sub.add_parser("restart")
    restart.add_argument("--mode", choices=["backend", "web", "full", "electron"], default="full")
    sub.add_parser("status")
    logs = sub.add_parser("logs")
    logs.add_argument("--service", default="bridge")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    orchestrator = create_orchestrator(args)
    if args.command == "status":
        print(json.dumps(orchestrator.status(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "stop":
        print(json.dumps(orchestrator.stop_all_registered(), ensure_ascii=False))
        return 0
    if args.command == "logs":
        path = ROOT / "logs" / f"{args.service}.log"
        print(path.read_text(encoding="utf-8")[-10000:] if path.exists() else "")
        return 0
    profile = args.mode
    if profile == "electron":
        raise SystemExit("electron mode is owned by Electron; use npm run electron:start")
    operation = orchestrator.restart if args.command == "restart" else orchestrator.start
    print(json.dumps(operation(profile), ensure_ascii=False))
    stopping = False

    def request_stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        while not stopping:
            time.sleep(0.5)
    finally:
        orchestrator.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
