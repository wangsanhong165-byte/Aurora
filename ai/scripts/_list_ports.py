"""List all service ports for cleanup by start_electron.bat.

Reads services.json and prints each service port on its own line
(excluding bridge and frontend, which are handled separately).
"""

import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "services.json"

EXCLUDED = {"bridge", "frontend"}

if __name__ == "__main__":
    try:
        config = json.loads(CONFIG_PATH.read_text("utf-8"))
        for name, svc in config.items():
            if name.startswith("_"):
                continue
            if name in EXCLUDED:
                continue
            port = svc.get("port")
            if port is not None:
                print(port)
    except Exception:
        pass
