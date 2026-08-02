from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock
from time import sleep

from app.lifecycle.control import ControlPlane, workspace_endpoint


class FakeOrchestrator:
    def __init__(self):
        self.calls = []

    def start(self, profile, *, launch_id, owner_id):
        self.calls.append(("start", profile, launch_id, owner_id))
        return {"availability": "TEXT_READY", "services": []}

    def status(self):
        return {"availability": "BLOCKED", "services": []}

    def stop_launch(self, launch_id):
        self.calls.append(("stop", launch_id))
        return self.status()


def test_control_plane_correlates_request_and_launch_identity():
    orchestrator = FakeOrchestrator()
    control = ControlPlane(orchestrator, token="secret")

    response = control.handle({
        "schema_version": 1,
        "token": "secret",
        "command": "start",
        "profile": "electron",
        "request_id": "request-1",
        "launch_id": "launch-1",
        "owner_id": "electron-1",
    })

    assert response["request_id"] == "request-1"
    assert response["launch_id"] == "launch-1"
    assert response["owner_id"] == "electron-1"
    assert response["ok"] is True
    assert orchestrator.calls == [("start", "electron", "launch-1", "electron-1")]


def test_control_plane_rejects_invalid_token_without_running_command():
    orchestrator = FakeOrchestrator()
    response = ControlPlane(orchestrator, token="secret").handle({
        "schema_version": 1,
        "token": "wrong",
        "command": "status",
        "request_id": "request-1",
    })

    assert response["ok"] is False
    assert response["recoverable"] is False
    assert orchestrator.calls == []


def test_workspace_endpoint_is_stable_and_does_not_expose_project_path(tmp_path: Path):
    first = workspace_endpoint(tmp_path)
    second = workspace_endpoint(tmp_path / ".")

    assert first == second
    assert str(tmp_path) not in first
    assert "soullink-lifecycle-" in first


def test_control_plane_serializes_mutating_commands():
    class ConcurrentOrchestrator(FakeOrchestrator):
        def __init__(self):
            super().__init__()
            self.active = 0
            self.maximum_active = 0
            self.lock = Lock()
            self.entered = Event()

        def start(self, profile, *, launch_id, owner_id):
            with self.lock:
                self.active += 1
                self.maximum_active = max(self.maximum_active, self.active)
            self.entered.set()
            sleep(0.05)
            with self.lock:
                self.active -= 1
            return {"availability": "FULL_READY", "services": []}

    orchestrator = ConcurrentOrchestrator()
    control = ControlPlane(orchestrator, token="secret")
    request = {
        "schema_version": 1,
        "token": "secret",
        "command": "start",
        "profile": "electron",
        "launch_id": "launch-1",
        "owner_id": "electron-1",
    }

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(control.handle, {**request, "request_id": "first"})
        orchestrator.entered.wait(timeout=1)
        second = pool.submit(control.handle, {**request, "request_id": "second"})
        assert first.result()["ok"] is True
        assert second.result()["ok"] is True

    assert orchestrator.maximum_active == 1
