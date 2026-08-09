import json
from pathlib import Path

from app.lifecycle.endpoints import EndpointResolver
from app.lifecycle.doctor import diagnose_endpoints
from app.lifecycle.manifest import Service, ServiceManifest
from app.lifecycle.orchestrator import LifecycleOrchestrator
from app.lifecycle.registry import ProcessIdentity, ProcessRegistry


class _Platform:
    def __init__(self, errors):
        self.errors = errors

    def port_owner(self, _port):
        return None

    def bind_error(self, _host, port):
        return self.errors.get(port)

    def allocate_port(self, _host, _claimed):
        return 24731


def test_endpoint_resolution_uses_a_fallback_when_windows_rejects_the_preferred_port():
    service = Service(
        name="llm",
        host="127.0.0.1",
        port=19202,
        fallback_ports=(19302,),
        command={"module": "app.modules.llm.api"},
    )
    resolver = EndpointResolver(
        _Platform({19202: PermissionError(10013, "port is excluded by Windows")})
    )

    plan = resolver.resolve([service])

    assert plan.services["llm"].port == 19302
    assert [
        (rejection.service_id, rejection.port, rejection.reason)
        for rejection in plan.rejections
    ] == [("llm", 19202, "excluded_or_denied")]


def test_endpoint_resolution_asks_the_os_for_a_port_when_all_named_candidates_fail():
    service = Service(
        name="bridge",
        host="127.0.0.1",
        port=19206,
        fallback_ports=(19306,),
        dynamic_port=True,
        command={"module": "app.bridge.server"},
    )
    resolver = EndpointResolver(_Platform({
        19206: PermissionError(10013, "excluded"),
        19306: OSError(10048, "occupied"),
    }))

    plan = resolver.resolve([service])

    assert plan.services["bridge"].port == 24731


def test_orchestrator_propagates_the_resolved_service_graph_before_spawning(tmp_path: Path):
    manifest_path = tmp_path / "services.json"
    manifest_path.write_text(json.dumps({
        "llm": {
            "host": "127.0.0.1",
            "port": 19202,
            "fallback_ports": [19302],
            "command": {
                "module": "app.modules.llm.api",
                "args": ["--port", "{port}"],
            },
        },
        "bridge": {
            "host": "127.0.0.1",
            "port": 19206,
            "command": {
                "module": "app.bridge.server",
                "args": ["--port", "{port}"],
            },
            "depends_on": ["llm"],
        },
    }), encoding="utf-8")

    class Process:
        def __init__(self, pid):
            self.pid = pid

        def poll(self):
            return None

    class Platform(_Platform):
        def __init__(self):
            super().__init__({
                19202: PermissionError(10013, "port is excluded by Windows"),
            })
            self.spawns = []

        def spawn(self, argv, _cwd, env, _log):
            process = Process(100 + len(self.spawns))
            self.spawns.append((argv, env))
            return process

        def identity(self, pid, port):
            return ProcessIdentity(pid, 1.0, "python.exe", ("python",), port)

    class Probe:
        def wait(self, _service, _process):
            return True

        def ready(self, _service):
            return True

    platform = Platform()
    orchestrator = LifecycleOrchestrator(
        tmp_path,
        ServiceManifest.load(manifest_path),
        registry=ProcessRegistry(tmp_path / "pids.json"),
        platform=platform,
        probe=Probe(),
    )

    result = orchestrator.start("backend")

    assert [spawn[0][-1] for spawn in platform.spawns] == ["19302", "19206"]
    assert platform.spawns[0][1]["LLM_URL"] == "http://127.0.0.1:19302"
    assert platform.spawns[0][1]["BRIDGE_URL"] == "http://127.0.0.1:19206"
    assert {service["id"]: service["port"] for service in result["services"]} == {
        "llm": 19302,
        "bridge": 19206,
    }


def test_endpoint_diagnostics_report_the_effective_fallback_without_starting_services(
    tmp_path: Path,
):
    manifest_path = tmp_path / "services.json"
    manifest_path.write_text(json.dumps({
        "bridge": {
            "host": "127.0.0.1",
            "port": 19206,
            "fallback_ports": [19306],
            "command": {"module": "app.bridge.server"},
        },
    }), encoding="utf-8")

    report = diagnose_endpoints(
        ServiceManifest.load(manifest_path),
        _Platform({19206: PermissionError(10013, "excluded")}),
    )

    assert report == {
        "ok": True,
        "services": [{
            "id": "bridge",
            "host": "127.0.0.1",
            "preferred_port": 19206,
            "port": 19306,
            "fallback": True,
        }],
        "rejections": [{
            "id": "bridge",
            "port": 19206,
            "reason": "excluded_or_denied",
            "detail": "[Errno 10013] excluded",
        }],
    }


def test_orchestrator_recovers_a_registered_service_on_its_previous_fallback(
    tmp_path: Path,
):
    manifest_path = tmp_path / "services.json"
    manifest_path.write_text(json.dumps({
        "llm": {
            "host": "127.0.0.1",
            "port": 19202,
            "fallback_ports": [19302],
            "command": {"module": "app.modules.llm.api"},
        },
    }), encoding="utf-8")
    identity = ProcessIdentity(321, 12.5, "python.exe", ("python", "llm"), 19302)
    registry = ProcessRegistry(tmp_path / "pids.json")
    registry.put("llm", identity)

    class Platform(_Platform):
        def __init__(self):
            super().__init__({})
            self.spawns = []

        def port_owner(self, port):
            return identity.pid if port == identity.port else None

        def identity(self, pid, port):
            return identity if (pid, port) == (identity.pid, identity.port) else None

        def spawn(self, *_args):
            self.spawns.append(_args)
            raise AssertionError("registered fallback service must be reused")

    class Probe:
        def ready(self, service):
            return service.port == identity.port

    orchestrator = LifecycleOrchestrator(
        tmp_path,
        ServiceManifest.load(manifest_path),
        registry=registry,
        platform=Platform(),
        probe=Probe(),
    )

    assert orchestrator.status()["services"][0]["port"] == 19302
    result = orchestrator.start("backend")

    assert result["services"][0]["port"] == 19302
    assert orchestrator.platform.spawns == []
