from __future__ import annotations

import os
from uuid import uuid4
from pathlib import Path
from urllib import request

from .health import HealthProbe
from .manifest import Service, ServiceManifest
from .platform import PlatformProcessAdapter
from .registry import ProcessIdentity, ProcessRegistry


class LifecycleError(RuntimeError):
    pass


class LifecycleOrchestrator:
    def __init__(
        self,
        root: Path,
        manifest: ServiceManifest,
        *,
        registry: ProcessRegistry | None = None,
        platform: PlatformProcessAdapter | None = None,
        probe: HealthProbe | None = None,
    ):
        self.root = root
        self.manifest = manifest
        self.registry = registry or ProcessRegistry(root / "data/pids/processes.json")
        self.platform = platform or PlatformProcessAdapter()
        self.probe = probe or HealthProbe()
        self.processes: dict[str, object] = {}
        self.logs: dict[str, object] = {}
        self.started: list[str] = []
        self.owner = uuid4().hex
        self.active_profile: str | None = None

    def start(self, profile: str = "backend") -> dict:
        self.active_profile = profile
        rollback_from = len(self.started)
        try:
            for service in self.manifest.for_profile(profile):
                self._start_service(service)
            return self.status()
        except Exception:
            self._stop_names(self.started[rollback_from:])
            raise

    def _start_service(self, service: Service) -> None:
        owner = self.platform.port_owner(service.port)
        if owner:
            actual = self.platform.identity(owner, service.port)
            if actual and self.registry.matches(service.name, actual) and self.probe.ready(service):
                return
            raise LifecycleError(
                f"{service.name}: port {service.port} is occupied by an external or unverified process"
            )
        log_dir = self.root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log = (log_dir / f"{service.name}.log").open("a", encoding="utf-8")
        env = os.environ.copy()
        env.update({
            key: value.replace("{root}", str(self.root)).replace(
                "{PATH}", env.get("PATH", "")
            )
            for key, value in service.env.items()
        })
        process = self.platform.spawn(
            service.argv(self.root),
            (self.root / service.cwd).resolve(),
            env,
            log,
        )
        identity = self.platform.identity(process.pid, service.port)
        if identity is None:
            raise LifecycleError(f"{service.name}: process exited during startup")
        self.processes[service.name] = process
        self.logs[service.name] = log
        self.registry.put(service.name, identity, self.owner)
        self.started.append(service.name)
        if not self.probe.wait(service, process):
            raise LifecycleError(f"{service.name}: readiness timeout")
        if service.warmup:
            self._warmup(service)

    def _warmup(self, service: Service) -> None:
        warmup = service.warmup or {}
        target = str(warmup.get("url", "")).format(host=service.host, port=service.port)
        payload = str(warmup.get("body", "{}")).encode()
        req = request.Request(target, data=payload, headers={"Content-Type": "application/json"})
        with request.urlopen(req, timeout=int(warmup.get("timeout", service.timeout))) as response:
            if response.status != 200:
                raise LifecycleError(f"{service.name}: warmup failed")

    def stop(self) -> dict:
        names = [
            name for name, entry in self.registry.items()
            if entry.get("owner") == self.owner
        ]
        self._stop_names(names)
        self.started.clear()
        self.processes.clear()
        return self.status()

    def stop_all_registered(self) -> dict:
        self._stop_names([name for name, _entry in self.registry.items()])
        return self.status()

    def _stop_names(self, names: list[str]) -> None:
        for name in reversed(names):
            entry = self.registry.get(name)
            if entry:
                identity = ProcessIdentity(
                    entry["pid"], entry["create_time"], entry["executable"],
                    tuple(entry["command"]), entry["port"],
                )
                actual = self.platform.identity(identity.pid, identity.port)
                if actual is None:
                    self.registry.remove(name)
                elif actual == identity and self.platform.terminate_tree(identity):
                    self.registry.remove(name)
            log = self.logs.pop(name, None)
            if log:
                log.close()
            if name in self.started:
                self.started.remove(name)

    def restart(self, profile: str = "backend") -> dict:
        self.stop()
        return self.start(profile)

    def status(self) -> dict:
        services = []
        for name, service in self.manifest.services.items():
            owner = self.platform.port_owner(service.port)
            state = "stopped"
            if owner:
                actual = self.platform.identity(owner, service.port)
                state = "running" if actual and self.registry.matches(name, actual) else "blocked_external"
            services.append({"name": name, "port": service.port, "status": state, "pid": owner})
        expected = {
            service.name for service in self.manifest.for_profile(self.active_profile)
        } if self.active_profile else set()
        return {
            "ready": bool(expected) and all(
                item["status"] == "running" for item in services if item["name"] in expected
            ),
            "services": services,
        }
