from __future__ import annotations

import os
from uuid import uuid4
from pathlib import Path
from urllib import request

from .health import HealthProbe
from .manifest import Service, ServiceManifest
from .platform import PlatformProcessAdapter
from .registry import ProcessIdentity, ProcessRegistry
from .protocol import AvailabilityLevel, EventStream
from .diagnostics import prune_launch_logs, rotate_log


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
        self.launch_id: str | None = None
        self.events: list[dict] = []
        self.stream: EventStream | None = None
        self._failed_services: set[str] = set()

    def start(
        self,
        profile: str = "backend",
        *,
        launch_id: str | None = None,
        owner_id: str | None = None,
    ) -> dict:
        if self.launch_id and self.started:
            current = self.status()
            if current["availability"] == AvailabilityLevel.FULL_READY.value:
                return current
        self.active_profile = profile
        self.launch_id = launch_id or self.launch_id or uuid4().hex
        self.owner = owner_id or self.owner
        self.stream = EventStream(self.launch_id, self.owner)
        prune_launch_logs(self.root)
        rollback_from = len(self.started)
        self._failed_services.clear()
        # Services with failure_policy="isolate" that time out are NOT rolled back.
        # Only abort-policy failures raise and trigger a full rollback.
        for service in self.manifest.for_profile(profile):
            try:
                self._start_service(service)
            except LifecycleError:
                self._failed_services.add(service.name)
                self._emit("service_state", service_id=service.name, state="failed")
                self._stop_names([service.name])
                if service.failure_policy != "isolate":
                    self._stop_names(self.started[rollback_from:])
                    raise
                # Log and continue for isolated services
                import logging
                logger = logging.getLogger("lifecycle.orchestrator")
                logger.warning(
                    "%s: failure_policy=isolate — proceeding without it",
                    service.name,
                )
        self._emit("availability", availability=self.status()["availability"])
        return self.status()

    def _start_service(self, service: Service) -> None:
        for dependency in service.depends_on:
            if dependency in self._failed_services or dependency not in self.started:
                raise LifecycleError(
                    f"{service.name}: dependency {dependency} is not ready"
                )
        owner = self.platform.port_owner(service.port)
        if owner:
            actual = self.platform.identity(owner, service.port)
            if actual and self.registry.matches(service.name, actual) and self.probe.ready(service):
                self.registry.put(service.name, actual, self.owner)
                if service.name not in self.started:
                    self.started.append(service.name)
                self._emit("service_state", service_id=service.name, state="ready")
                return
            raise LifecycleError(
                f"{service.name}: port {service.port} is occupied by an external or unverified process"
            )
        bind_error = getattr(self.platform, "bind_error", lambda _host, _port: None)(
            service.host, service.port
        )
        if bind_error is not None:
            raise LifecycleError(
                f"{service.name}: cannot bind {service.host}:{service.port}: {bind_error}"
            )
        log_dir = self.root / "logs" / "launches" / (self.launch_id or "legacy") / "services"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{service.name}.log"
        rotate_log(log_path)
        log = log_path.open("a", encoding="utf-8")
        self._emit("service_state", service_id=service.name, state="spawning")
        env = os.environ.copy()
        python_dir = str(Path(service.python or "").parent)
        env.update({
            key: (
                value.replace("{root}", str(self.root))
                .replace("{python_dir}", python_dir)
                .replace("{PATH}", env.get("PATH", ""))
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
        if service.name not in self.started:
            self.started.append(service.name)
        self._emit("service_state", service_id=service.name, state="running")
        if not self.probe.wait(service, process):
            raise LifecycleError(f"{service.name}: readiness timeout")
        if service.warmup:
            self._emit("service_state", service_id=service.name, state="warming")
            try:
                self._warmup(service)
            except Exception as exc:
                if isinstance(exc, LifecycleError):
                    raise
                raise LifecycleError(f"{service.name}: warmup failed: {exc}") from exc
        self._emit("service_state", service_id=service.name, state="ready")

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

    def stop_launch(self, launch_id: str) -> dict:
        if not launch_id:
            raise LifecycleError("launch_id is required; use --all explicitly to stop all launches")
        if self.launch_id and launch_id != self.launch_id:
            return self.status()
        return self.stop()

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
        """Return a fresh snapshot so child exits are visible immediately."""
        return self._build_status()

    def _build_status(self) -> dict:
        services = []
        for name, service in self.manifest.services.items():
            owner = self.platform.port_owner(service.port)
            state = "stopped"
            if name in self._failed_services:
                state = "failed"
            elif owner:
                actual = self.platform.identity(owner, service.port)
                if actual and self.registry.matches(name, actual):
                    state = "ready" if self.probe.ready(service) else "running"
                else:
                    state = "blocked_external"
            services.append({
                "id": name,
                "name": name,
                "display_name": service.display_name or name,
                "category": service.category,
                "provider": service.provider,
                "required": any(name in item.required_services for item in self.manifest.capabilities.values()),
                "status": state,
                "port": service.port,
                "pid": owner,
            })
        expected = {
            service.name for service in self.manifest.for_profile(self.active_profile)
        } if self.active_profile else set()
        state_map = {item["name"]: item["status"] for item in services}
        availability = self.manifest.availability(state_map)
        capabilities = [{
            "id": capability.name,
            "display_name": capability.display_name,
            "minimum_level": capability.minimum_level.value,
            "state": (
                "ready"
                if all(state_map.get(name) in {"ready", "degraded", "failed"} for name in capability.required_services)
                else "warming"
            ),
        } for capability in self.manifest.capabilities.values()]
        return {
            "schema_version": 1,
            "launch_id": self.launch_id,
            "owner_id": self.owner,
            "availability": availability.value,
            "ready": availability != AvailabilityLevel.BLOCKED,
            "services": services,
            "capabilities": capabilities,
            "events": self.events[-200:],
        }

    def _emit(self, event_type: str, **payload) -> None:
        if self.stream:
            self.events.append(self.stream.event(event_type, **payload))
