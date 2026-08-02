from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import psutil


def process_snapshot(pid: int) -> dict[str, Any] | None:
    try:
        process = psutil.Process(pid)
        return {
            "pid": process.pid,
            "create_time": process.create_time(),
            "executable": process.exe(),
            "command": process.cmdline(),
            "cwd": process.cwd(),
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
        return None


def snapshot_matches(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
    try:
        expected_cwd = str(Path(expected.get("cwd", "")).resolve()).lower()
        actual_cwd = str(Path(actual.get("cwd", "")).resolve()).lower()
        return (
            int(expected.get("pid", -1)) == int(actual.get("pid", -2))
            and abs(
                float(expected.get("create_time", -1))
                - float(actual.get("create_time", -2))
            ) < 0.01
            and str(expected.get("executable", "")).lower()
            == str(actual.get("executable", "")).lower()
            and list(expected.get("command", [])) == list(actual.get("command", []))
            and expected_cwd == actual_cwd
        )
    except (TypeError, ValueError, OSError):
        return False
