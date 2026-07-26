import json
from pathlib import Path

import pytest

from app.lifecycle.manifest import ManifestError, ServiceManifest
from app.lifecycle.registry import ProcessIdentity, ProcessRegistry
from app.lifecycle.orchestrator import LifecycleError, LifecycleOrchestrator
from app.lifecycle.protocol import AvailabilityLevel, EventStream


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


def test_manifest_exposes_dynamic_capabilities_and_service_python(tmp_path: Path):
    default_python = tmp_path / "runtime-python.exe"
    voice_python = tmp_path / "voice-python.exe"
    path = tmp_path / "services.json"
    path.write_text(json.dumps({
        "_meta": {
            "capabilities": {
                "text": {
                    "display_name": "文本交流",
                    "minimum_level": "TEXT_READY",
                    "required_services": ["bridge"],
                },
                "voice": {
                    "display_name": "语音交流",
                    "minimum_level": "VOICE_READY",
                    "required_services": ["voice"],
                    "degraded_without": ["voice"],
                },
            }
        },
        "bridge": {
            "display_name": "角色连接",
            "category": "text",
            "port": 10001,
            "command": {"module": "bridge"},
            "profiles": ["backend"],
        },
        "voice": {
            "display_name": "语音合成",
            "category": "voice",
            "port": 10002,
            "command": {"module": "voice"},
            "profiles": ["backend"],
        },
    }), encoding="utf-8")
    manifest = ServiceManifest.load(
        path,
        runtime_config={
            "python": {
                "default": str(default_python),
                "services": {"voice": str(voice_python)},
            }
        },
    )

    assert manifest.get("bridge").display_name == "角色连接"
    assert manifest.get("bridge").argv(tmp_path)[0] == str(default_python)
    assert manifest.get("voice").argv(tmp_path)[0] == str(voice_python)
    assert manifest.capabilities["text"].display_name == "文本交流"


def test_availability_levels_allow_text_while_voice_is_warming(tmp_path: Path):
    path = tmp_path / "services.json"
    path.write_text(json.dumps({
        "_meta": {
            "capabilities": {
                "text": {
                    "display_name": "文本交流",
                    "minimum_level": "TEXT_READY",
                    "required_services": ["bridge"],
                },
                "voice": {
                    "display_name": "语音交流",
                    "minimum_level": "VOICE_READY",
                    "required_services": ["voice"],
                },
            }
        },
        "bridge": {"port": 10001, "command": {"module": "bridge"}},
        "voice": {"port": 10002, "command": {"module": "voice"}},
    }), encoding="utf-8")
    manifest = ServiceManifest.load(path)

    assert manifest.availability({"bridge": "ready", "voice": "warming"}) == AvailabilityLevel.TEXT_READY
    assert manifest.availability({"bridge": "ready", "voice": "ready"}) == AvailabilityLevel.FULL_READY


def test_event_stream_assigns_protocol_identity_and_monotonic_sequence():
    stream = EventStream("launch-1", "owner-1")
    first = stream.event("service_state", service_id="bridge", attempt=1)
    second = stream.event("availability", availability="TEXT_READY")

    assert first["schema_version"] == 1
    assert first["launch_id"] == "launch-1"
    assert first["owner_id"] == "owner-1"
    assert first["event_id"] != second["event_id"]
    assert [first["sequence"], second["sequence"]] == [1, 2]
    assert first["recoverable"] is True
    assert "recommended_action" in first
