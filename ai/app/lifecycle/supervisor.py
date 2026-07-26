from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .manifest import ServiceManifest
from .orchestrator import LifecycleOrchestrator
from .control import ControlServer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    runtime_config = {}
    runtime_path = root / "config/runtime.local.json"
    if runtime_path.exists():
        runtime_config = json.loads(runtime_path.read_text(encoding="utf-8"))
    orchestrator = LifecycleOrchestrator(
        root,
        ServiceManifest.load(
            root / "config/services.json",
            runtime_config=runtime_config,
        ),
    )
    if args.serve:
        ControlServer(root, orchestrator).serve()
        return 0
    try:
        for line in sys.stdin:
            try:
                request = json.loads(line)
                command = request.get("command")
                if command == "start":
                    result = orchestrator.start(request.get("profile", "electron"))
                elif command == "restart":
                    result = orchestrator.restart(request.get("profile", "electron"))
                elif command == "stop":
                    result = orchestrator.stop()
                elif command == "status":
                    result = orchestrator.status()
                else:
                    raise ValueError(f"unknown command: {command}")
                response = {"id": request.get("id"), "ok": True, "result": result}
            except Exception as error:
                response = {"id": request.get("id") if "request" in locals() else None, "ok": False, "error": str(error)}
            print(json.dumps(response), flush=True)
    except (OSError, EOFError):
        pass
    finally:
        orchestrator.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
