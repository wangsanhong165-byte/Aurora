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
    """Recover only processes whose persisted identity belongs to this workspace.

    Stale records are always cleared — a launch that reaches recovery has
    already established that the recorded Supervisor is not serving, so the
    record itself is definitively stale. A process is terminated only when its
    persisted identity is positively confirmed to belong to this workspace; a
    reused PID (or any unverifiable process) is never killed, and clearing the
    stale record is what unblocks the next launch.
    """
    root = root.resolve()
    recovered: list[str] = []

    electron_pid_path = root / "data" / "pids" / "electron.pid"
    if electron_pid_path.exists():
        try:
            electron_pid = int(electron_pid_path.read_text(encoding="utf-8").strip())
        except ValueError:
            electron_pid = 0
        if electron_pid:
            try:
                electron = psutil.Process(electron_pid)
            except psutil.NoSuchProcess:
                electron = None
            if electron is not None and _is_workspace_electron(electron, root):
                _terminate_process_tree(electron)
                recovered.append(f"electron:{electron_pid}")
            # A reused PID or a foreign Electron is left untouched; only our
            # stale pid file is dropped below.
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
            # A reused PID or drifted identity must never be terminated. Drop
            # the stale entry so the next launch re-registers the service.
            registry.remove(name)

    control_path = root / "data" / "runtime" / "lifecycle-control.json"
    if control_path.exists():
        try:
            record = json.loads(control_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            record = {}
        supervisor_pid = int(record.get("pid", 0) or 0)
        if supervisor_pid:
            try:
                supervisor = psutil.Process(supervisor_pid)
            except psutil.NoSuchProcess:
                supervisor = None
            if supervisor is not None:
                recorded_create_time = record.get("create_time")
                try:
                    actual_create_time = supervisor.create_time()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    actual_create_time = None
                same_process = (
                    recorded_create_time is not None
                    and actual_create_time is not None
                    and abs(recorded_create_time - actual_create_time) < 0.01
                )
                signature_match = _command_contains(
                    supervisor, "-m", "app.lifecycle.supervisor", "--serve"
                )
                # Kill only a positively-identified orphan: either create_time
                # matches (authoritative), or a legacy record without create_time
                # is corroborated by the command-line signature.
                if same_process or (recorded_create_time is None and signature_match):
                    _terminate_process_tree(supervisor)
                    recovered.append(f"supervisor:{supervisor_pid}")
                # Otherwise the PID was reused by an unrelated process — leave
                # it alone; the stale record is cleared below regardless.
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
