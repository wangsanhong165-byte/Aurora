from __future__ import annotations

from pathlib import Path

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
