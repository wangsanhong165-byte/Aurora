from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import uuid4

from .control import send_request
from .process_identity import process_snapshot
from .protocol import SCHEMA_VERSION


def main() -> int:
    parser = argparse.ArgumentParser(description="SoulLink lifecycle control client")
    parser.add_argument(
        "command",
        choices=[
            "start", "stop", "restart", "status", "events", "diagnostics",
            "shutdown", "process-info",
        ],
    )
    parser.add_argument("--profile", default="backend")
    parser.add_argument("--launch-id", default="")
    parser.add_argument("--owner-id", default="")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--after-sequence", type=int, default=0)
    parser.add_argument("--pid", type=int, default=None)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    if args.command == "process-info":
        if args.pid is None:
            parser.error("process-info requires --pid")
        snapshot = process_snapshot(args.pid)
        if snapshot is None:
            return 1
        print(json.dumps(snapshot, ensure_ascii=False))
        return 0
    response = send_request(args.root, {
        "schema_version": SCHEMA_VERSION,
        "command": args.command,
        "profile": args.profile,
        "launch_id": args.launch_id,
        "owner_id": args.owner_id,
        "request_id": uuid4().hex,
        "all": args.all,
        "after_sequence": args.after_sequence,
    })
    print(json.dumps(response, ensure_ascii=False))
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
