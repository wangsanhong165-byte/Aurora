from __future__ import annotations

import json
import sys
from pathlib import Path

from .manifest import ServiceManifest
from .orchestrator import LifecycleOrchestrator


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    orchestrator = LifecycleOrchestrator(
        root, ServiceManifest.load(root / "config/services.json")
    )
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
    finally:
        orchestrator.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
