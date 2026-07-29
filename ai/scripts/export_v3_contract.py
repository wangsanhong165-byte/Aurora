"""Export or verify the canonical V3 runtime event contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.v3.envelope import CANONICAL_ENVELOPE_FIELDS, PROTOCOL_VERSION
from contracts.v3.events import EVENT_PAYLOAD_MODELS, TURN_EVENT_TYPES


OUTPUT = ROOT / "contracts" / "v3" / "runtime-events.schema.json"


def build_contract() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Companion Runtime V3 Events",
        "protocolVersion": PROTOCOL_VERSION,
        "envelope": {
            "type": "object",
            "additionalProperties": False,
            "required": list(CANONICAL_ENVELOPE_FIELDS),
            "properties": {
                "protocolVersion": {"const": PROTOCOL_VERSION},
                "eventId": {"type": "string", "minLength": 1},
                "eventType": {"enum": sorted(EVENT_PAYLOAD_MODELS)},
                "sessionId": {"type": "string", "minLength": 1},
                "turnId": {"type": ["string", "null"]},
                "sequence": {"type": "integer", "minimum": 1},
                "source": {
                    "enum": ["frontend", "runtime", "bridge", "lifecycle", "platform"],
                },
                "timestamp": {"type": "number", "exclusiveMinimum": 0},
                "payload": {"type": "object"},
            },
        },
        "events": {
            event_type: {
                "scope": "turn" if event_type in TURN_EVENT_TYPES else "system",
                "payload": model.model_json_schema(by_alias=True),
            }
            for event_type, model in sorted(EVENT_PAYLOAD_MODELS.items())
        },
    }


def render_contract() -> str:
    return json.dumps(build_contract(), ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    rendered = render_contract()
    if args.write:
        OUTPUT.write_text(rendered, encoding="utf-8")
        print(f"wrote {OUTPUT}")
        return 0

    current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
    if current != rendered:
        print(f"{OUTPUT} is out of date")
        return 1
    print(f"{OUTPUT} is current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
