from __future__ import annotations

import argparse
import json
from pathlib import Path

from .endpoints import EndpointResolutionError, EndpointResolver
from .manifest import ServiceManifest
from .platform import PlatformProcessAdapter


def diagnose_endpoints(manifest: ServiceManifest, platform) -> dict:
    """Report the launch endpoints without spawning or stopping any process."""
    preferred = {name: service.port for name, service in manifest.services.items()}
    try:
        plan = EndpointResolver(platform).resolve(manifest.services.values())
    except EndpointResolutionError as exc:
        return {"ok": False, "error": str(exc), "services": [], "rejections": []}

    return {
        "ok": True,
        "services": [
            {
                "id": name,
                "host": service.host,
                "preferred_port": preferred[name],
                "port": service.port,
                "fallback": service.port != preferred[name],
            }
            for name, service in plan.services.items()
        ],
        "rejections": [
            {
                "id": rejection.service_id,
                "port": rejection.port,
                "reason": rejection.reason,
                "detail": rejection.detail,
            }
            for rejection in plan.rejections
        ],
    }


def load_manifest(root: Path) -> ServiceManifest:
    runtime_config = {}
    runtime_path = root / "config/runtime.local.json"
    if runtime_path.exists():
        runtime_config = json.loads(runtime_path.read_text(encoding="utf-8"))
    return ServiceManifest.load(
        root / "config/services.json",
        runtime_config=runtime_config,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Check SoulLink launch endpoints")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    args = parser.parse_args()
    report = diagnose_endpoints(load_manifest(args.root), PlatformProcessAdapter())
    for rejection in report["rejections"]:
        print(
            f"[PORT] {rejection['id']} rejected {rejection['port']} "
            f"({rejection['reason']}): {rejection['detail']}"
        )
    for service in report["services"]:
        marker = "FALLBACK" if service["fallback"] else "OK"
        print(f"[{marker}] {service['id']}: {service['host']}:{service['port']}")
    if not report["ok"]:
        print(f"[FAIL] {report['error']}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
