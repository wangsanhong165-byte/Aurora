import json
from pathlib import Path

import pytest

from app.lifecycle.manifest import ManifestError, ServiceManifest
from app.lifecycle.registry import ProcessIdentity, ProcessRegistry
from app.lifecycle.orchestrator import LifecycleError, LifecycleOrchestrator


def test_manifest_orders_dependencies_and_applies_overrides(tmp_path: Path):
    path = tmp_path / "services.json"
    path.write_text(json.dumps({
        "engine": {"port": 1, "command": {"module": "engine"}, "profiles": ["backend"]},
        "adapter": {
            "port": 2,
            "command": {"module": "adapter"},
            "depends_on": ["engine"],
            "profiles": ["backend"],
        },
    }), encoding="utf-8")
    manifest = ServiceManifest.load(path, env={"ADAPTER_PORT": "42"})
    assert [service.name for service in manifest.for_profile("backend")] == ["engine", "adapter"]
    assert manifest.get("adapter").port == 42


def test_manifest_rejects_dependency_cycles(tmp_path: Path):
    path = tmp_path / "services.json"
    path.write_text(json.dumps({
        "a": {"port": 1, "command": {"module": "a"}, "depends_on": ["b"]},
        "b": {"port": 2, "command": {"module": "b"}, "depends_on": ["a"]},
    }), encoding="utf-8")
    with pytest.raises(ManifestError, match="cycle"):
        ServiceManifest.load(path)


def test_registry_rejects_reused_pid_identity(tmp_path: Path):
    registry = ProcessRegistry(tmp_path / "processes.json")
    expected = ProcessIdentity(10, 100.0, "python", ("-m", "app.modules.llm.api"), 9102)
    registry.put("llm", expected)
    reused = ProcessIdentity(10, 200.0, "other.exe", ("unrelated",), 9102)
    assert not registry.matches("llm", reused)


def test_orchestrator_does_not_kill_unknown_port_owner(tmp_path: Path):
    path = tmp_path / "services.json"
    path.write_text(json.dumps({
        "bridge": {"port": 9528, "command": {"module": "bridge"}, "profiles": ["backend"]}
    }), encoding="utf-8")

    class Platform:
        terminated = []
        def port_owner(self, _port): return 99
        def identity(self, pid, port):
            return ProcessIdentity(pid, 1.0, "external.exe", ("external",), port)
        def terminate_tree(self, identity):
            self.terminated.append(identity)
            return True

    platform = Platform()
    orchestrator = LifecycleOrchestrator(
        tmp_path, ServiceManifest.load(path),
        registry=ProcessRegistry(tmp_path / "pids.json"), platform=platform,
    )
    with pytest.raises(LifecycleError, match="external or unverified"):
        orchestrator.start("backend")
    assert platform.terminated == []
