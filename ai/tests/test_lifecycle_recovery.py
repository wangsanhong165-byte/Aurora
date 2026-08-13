"""Recovery must clear stale records without ever killing a reused PID.

The recovery path runs only after `status` has already established that the
recorded Supervisor is not serving, so the record itself is always stale. The
safety invariant under test is: a process is terminated only when its persisted
identity is positively confirmed, and a reused PID (or any unverifiable
process) is left untouched while its stale record is dropped.
"""

import json
from pathlib import Path

import app.lifecycle.recovery as recovery
from app.lifecycle.registry import ProcessIdentity, ProcessRegistry


class _FakeProcess:
    def __init__(self, pid, *, create_time, cmdline, exe="python.exe"):
        self.pid = pid
        self._create_time = create_time
        self._cmdline = cmdline
        self._exe = exe

    def create_time(self):
        return self._create_time

    def cmdline(self):
        return self._cmdline

    def exe(self):
        return self._exe


def _write_control_record(root: Path, payload: dict) -> Path:
    path = root / "data" / "runtime" / "lifecycle-control.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_recovery_clears_reused_supervisor_pid_without_killing(tmp_path, monkeypatch):
    record = _write_control_record(tmp_path, {"pid": 9999, "create_time": 100.0})

    # The PID is alive but belongs to an unrelated process now (create_time
    # differs and the command line is not a Supervisor).
    fake = _FakeProcess(9999, create_time=200.0, cmdline=["Nahimic3.exe"])
    monkeypatch.setattr(recovery.psutil, "Process", lambda _pid: fake)

    killed = []
    monkeypatch.setattr(
        recovery, "_terminate_process_tree", lambda proc: killed.append(proc.pid)
    )

    recovered = recovery.recover_stale_runtime(tmp_path)

    assert killed == []
    assert "supervisor:9999" not in recovered
    assert not record.exists()


def test_recovery_kills_verified_orphan_supervisor(tmp_path, monkeypatch):
    record = _write_control_record(tmp_path, {"pid": 9999, "create_time": 100.0})

    fake = _FakeProcess(
        9999,
        create_time=100.0,
        cmdline=["python", "-m", "app.lifecycle.supervisor", "--serve"],
    )
    monkeypatch.setattr(recovery.psutil, "Process", lambda _pid: fake)

    killed = []
    monkeypatch.setattr(
        recovery, "_terminate_process_tree", lambda proc: killed.append(proc.pid)
    )

    recovered = recovery.recover_stale_runtime(tmp_path)

    assert killed == [9999]
    assert "supervisor:9999" in recovered
    assert not record.exists()


def test_recovery_kills_legacy_supervisor_record_by_cmdline(tmp_path, monkeypatch):
    # Legacy records carry no create_time; the command-line signature is the
    # only corroboration available.
    record = _write_control_record(tmp_path, {"pid": 9999})

    fake = _FakeProcess(
        9999,
        create_time=100.0,
        cmdline=["python", "-m", "app.lifecycle.supervisor", "--serve"],
    )
    monkeypatch.setattr(recovery.psutil, "Process", lambda _pid: fake)

    killed = []
    monkeypatch.setattr(
        recovery, "_terminate_process_tree", lambda proc: killed.append(proc.pid)
    )

    recovered = recovery.recover_stale_runtime(tmp_path)

    assert killed == [9999]
    assert "supervisor:9999" in recovered
    assert not record.exists()


def test_recovery_clears_legacy_reused_pid_without_killing(tmp_path, monkeypatch):
    record = _write_control_record(tmp_path, {"pid": 9999})

    fake = _FakeProcess(9999, create_time=100.0, cmdline=["unrelated.exe"])
    monkeypatch.setattr(recovery.psutil, "Process", lambda _pid: fake)

    killed = []
    monkeypatch.setattr(
        recovery, "_terminate_process_tree", lambda proc: killed.append(proc.pid)
    )

    recovered = recovery.recover_stale_runtime(tmp_path)

    assert killed == []
    assert not record.exists()


def test_recovery_clears_dead_supervisor_pid(tmp_path, monkeypatch):
    record = _write_control_record(tmp_path, {"pid": 9999, "create_time": 100.0})

    def raise_no_such_process(_pid):
        raise recovery.psutil.NoSuchProcess(9999)

    monkeypatch.setattr(recovery.psutil, "Process", raise_no_such_process)

    recovered = recovery.recover_stale_runtime(tmp_path)

    assert recovered == []
    assert not record.exists()


def test_recovery_clears_foreign_electron_pid_without_killing(tmp_path, monkeypatch):
    pid_path = tmp_path / "data" / "pids" / "electron.pid"
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("9999", encoding="utf-8")

    fake = _FakeProcess(
        9999, create_time=100.0, cmdline=["notepad.exe"], exe="C:\\Windows\\notepad.exe"
    )
    monkeypatch.setattr(recovery.psutil, "Process", lambda _pid: fake)
    monkeypatch.setattr(recovery, "_is_workspace_electron", lambda _proc, _root: False)

    killed = []
    monkeypatch.setattr(
        recovery, "_terminate_process_tree", lambda proc: killed.append(proc.pid)
    )

    recovered = recovery.recover_stale_runtime(tmp_path)

    assert killed == []
    assert not pid_path.exists()


def test_recovery_removes_drifted_service_identity_without_killing(tmp_path, monkeypatch):
    registry_path = tmp_path / "data" / "pids" / "processes.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    stored = ProcessIdentity(100, 1.0, "python.exe", ("python", "-m", "llm"), 9102)
    registry = ProcessRegistry(registry_path)
    registry.put("llm", stored)

    # The PID now resolves to a different process (reused PID / drifted identity).
    drifted = ProcessIdentity(100, 2.0, "other.exe", ("other",), 9102)

    class FakeAdapter:
        terminated = []

        def identity(self, pid, port):
            return drifted

        def terminate_tree(self, identity):
            self.terminated.append(identity.pid)
            return True

    fake_adapter = FakeAdapter()
    monkeypatch.setattr(recovery, "PlatformProcessAdapter", lambda: fake_adapter)

    recovered = recovery.recover_stale_runtime(tmp_path)

    assert fake_adapter.terminated == []
    assert registry.get("llm") is None
