from __future__ import annotations

import json
import os
import platform
import re
import sys
import zipfile
from pathlib import Path


SECRET_PATTERN = re.compile(
    r"(token|secret|password|api[_-]?key|authorization)",
    re.IGNORECASE,
)


def redact(value):
    if isinstance(value, dict):
        return {
            key: ("[REDACTED]" if SECRET_PATTERN.search(key) else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def export_diagnostics(root: Path, snapshot: dict) -> Path:
    launch_id = snapshot.get("launch_id") or "no-launch"
    launch_dir = root / "logs" / "launches" / launch_id
    launch_dir.mkdir(parents=True, exist_ok=True)
    target = launch_dir / f"diagnostics-{launch_id}.zip"
    manifest = json.loads((root / "config/services.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(
            "snapshot.json",
            json.dumps(redact(snapshot), ensure_ascii=False, indent=2),
        )
        bundle.writestr(
            "services.json",
            json.dumps(redact(manifest), ensure_ascii=False, indent=2),
        )
        bundle.writestr("system.json", json.dumps({
            "python": sys.version,
            "platform": platform.platform(),
            "cwd": "[WORKSPACE]",
        }, indent=2))
        for log in launch_dir.rglob("*.log"):
            content = log.read_text(encoding="utf-8", errors="replace")[-200_000:]
            content = content.replace(str(root), "[WORKSPACE]")
            bundle.writestr(str(log.relative_to(launch_dir)), content)
    return target


def prune_launch_logs(root: Path, *, keep_days: int = 14, keep_launches: int = 20) -> None:
    base = root / "logs" / "launches"
    if not base.exists():
        return
    directories = sorted(
        (item for item in base.iterdir() if item.is_dir()),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    cutoff = __import__("time").time() - keep_days * 86400
    for item in directories[keep_launches:]:
        if item.stat().st_mtime >= cutoff:
            continue
        for child in sorted(item.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        item.rmdir()


def rotate_log(path: Path, *, max_bytes: int = 10 * 1024 * 1024, backups: int = 3) -> None:
    if not path.exists() or path.stat().st_size < max_bytes:
        return
    oldest = path.with_suffix(path.suffix + f".{backups}")
    oldest.unlink(missing_ok=True)
    for index in range(backups - 1, 0, -1):
        source = path.with_suffix(path.suffix + f".{index}")
        if source.exists():
            source.replace(path.with_suffix(path.suffix + f".{index + 1}"))
    path.replace(path.with_suffix(path.suffix + ".1"))
