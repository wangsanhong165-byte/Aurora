from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import psutil

from .platform import PlatformProcessAdapter
from .registry import ProcessIdentity, ProcessRegistry


def _command_contains(process: psutil.Process, *parts: str) -> bool:
    try:
        command = [str(part).lower() for part in process.cmdline()]
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
    return all(any(expected.lower() == item for item in command) for expected in parts)


def _is_workspace_electron(process: psutil.Process, root: Path) -> bool:
    expected = (
        root / "frontend" / "node_modules" / "electron" / "dist" / "electron.exe"
    ).resolve()
    try:
        return Path(process.exe()).resolve() == expected
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return False


def _terminate_process_tree(process: psutil.Process) -> None:
    try:
        children = process.children(recursive=True)
        for child in reversed(children):
            try:
                child.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                # Chromium utility processes can be protected independently.
                # Closing the verified Electron parent normally releases them.
                pass
        _gone, alive = psutil.wait_procs(children, timeout=3)
        for child in alive:
            try:
                child.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        process.terminate()
        try:
            process.wait(timeout=5)
        except psutil.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    except psutil.NoSuchProcess:
        return


def recover_stale_runtime(root: Path) -> list[str]:
    """Recover only processes whose persisted identity belongs to this workspace."""
    root = root.resolve()
    recovered: list[str] = []

    electron_pid_path = root / "data" / "pids" / "electron.pid"
    if electron_pid_path.exists():
        try:
            electron_pid = int(electron_pid_path.read_text(encoding="utf-8").strip())
            electron = psutil.Process(electron_pid)
            if not _is_workspace_electron(electron, root):
                raise RuntimeError(
                    f"refusing to stop PID {electron_pid}: it is not this workspace's Electron"
                )
            _terminate_process_tree(electron)
            recovered.append(f"electron:{electron_pid}")
        except psutil.NoSuchProcess:
            pass
        electron_pid_path.unlink(missing_ok=True)

    registry = ProcessRegistry(root / "data" / "pids" / "processes.json")
    platform = PlatformProcessAdapter()
    for name, entry in registry.items():
        identity = ProcessIdentity(
            entry["pid"], entry["create_time"], entry["executable"],
            tuple(entry["command"]), entry["port"],
        )
        actual = platform.identity(identity.pid, identity.port)
        if actual is None:
            registry.remove(name)
        elif actual == identity and platform.terminate_tree(identity):
            registry.remove(name)
            recovered.append(f"service:{name}:{identity.pid}")
        else:
            raise RuntimeError(
                f"refusing to stop PID {identity.pid}: persisted identity for {name} no longer matches"
            )

    control_path = root / "data" / "runtime" / "lifecycle-control.json"
    if control_path.exists():
        record = json.loads(control_path.read_text(encoding="utf-8"))
        supervisor_pid = int(record.get("pid", 0))
        if supervisor_pid:
            try:
                supervisor = psutil.Process(supervisor_pid)
                if not _command_contains(
                    supervisor, "-m", "app.lifecycle.supervisor", "--serve"
                ):
                    raise RuntimeError(
                        f"refusing to stop PID {supervisor_pid}: it is not a SoulLink Supervisor"
                    )
                _terminate_process_tree(supervisor)
                recovered.append(f"supervisor:{supervisor_pid}")
            except psutil.NoSuchProcess:
                pass
        control_path.unlink(missing_ok=True)

    return recovered


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover a verified stale SoulLink runtime")
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    args = parser.parse_args()
    try:
        recovered = recover_stale_runtime(args.root)
    except (RuntimeError, OSError, psutil.Error) as exc:
        print(f"[FAILED] Safe runtime recovery stopped: {exc}", file=sys.stderr)
        return 1
    if recovered:
        print("[RECOVERED] " + ", ".join(recovered))
    else:
        print("[OK] No stale SoulLink processes were found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
