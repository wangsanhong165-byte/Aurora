from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from .protocol import AvailabilityLevel


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class Service:
    name: str
    host: str
    port: int
    command: Mapping[str, object]
    fallback_ports: tuple[int, ...] = ()
    dynamic_port: bool = False
    health: str | None = None
    timeout: int = 30
    depends_on: tuple[str, ...] = ()
    profiles: tuple[str, ...] = ("backend",)
    cwd: str = "."
    readiness: bool = False
    warmup: Mapping[str, object] | None = None
    env: Mapping[str, str] = field(default_factory=dict)
    display_name: str = ""
    category: str = "system"
    provider: str | None = None
    python: str | None = None
    startup_priority: int = 100
    failure_policy: str = "abort"  # "abort" — exception raises, profile stops
                                   # "isolate" — logged, other services continue

    def argv(self, root: Path) -> list[str]:
        command = self.command
        executable = (
            str(command.get("executable", "{python}"))
            .replace("{python}", self.python or sys.executable)
            .replace("{root}", str(root))
        )
        if "module" in command:
            argv = [executable, "-m", str(command["module"])]
        else:
            script = str(command["script"]).replace("{root}", str(root))
            argv = [executable, script]
        for value in command.get("args", []):
            argv.append(
                str(value)
                .replace("{root}", str(root))
                .replace("{host}", self.host)
                .replace("{port}", str(self.port))
            )
        return argv

    @property
    def port_candidates(self) -> tuple[int, ...]:
        """Return the preferred port followed by unique configured fallbacks."""
        return tuple(dict.fromkeys((self.port, *self.fallback_ports)))


@dataclass(frozen=True)
class Capability:
    name: str
    display_name: str
    minimum_level: AvailabilityLevel
    required_services: tuple[str, ...]
    optional_services: tuple[str, ...] = ()
    degraded_without: tuple[str, ...] = ()


class ServiceManifest:
    def __init__(self, services: dict[str, Service], capabilities: dict[str, Capability] | None = None):
        self.services = services
        self.capabilities = capabilities or {}
        self._validate()

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        env: Mapping[str, str] | None = None,
        overrides: Mapping[str, Mapping[str, object]] | None = None,
        cli_overrides: Mapping[str, Mapping[str, object]] | None = None,
        runtime_config: Mapping[str, object] | None = None,
    ) -> "ServiceManifest":
        raw = json.loads(path.read_text(encoding="utf-8"))
        metadata = raw.get("_meta", {})
        environment = env if env is not None else os.environ
        python_config = (runtime_config or {}).get("python", {})
        if isinstance(python_config, str):
            python_config = {"default": python_config}
        python_default = str(python_config.get("default", sys.executable))
        python_services = python_config.get("services", {})
        services: dict[str, Service] = {}
        for name, value in raw.items():
            if name.startswith("_"):
                continue
            merged = dict(value)
            merged.update((overrides or {}).get(name, {}))
            env_port = environment.get(f"{name.upper()}_PORT", merged["port"])
            env_host = environment.get(f"{name.upper()}_HOST", merged.get("host", "127.0.0.1"))
            cli = (cli_overrides or {}).get(name, {})
            merged.update(cli)
            port = int(cli.get("port", env_port))
            host = str(cli.get("host", env_host))
            services[name] = Service(
                name=name,
                host=host,
                port=port,
                command=merged.get("command", {"module": f"app.modules.{name}.api"}),
                fallback_ports=tuple(int(item) for item in merged.get("fallback_ports", [])),
                dynamic_port=bool(merged.get("dynamic_port", False)),
                health=merged.get("health"),
                timeout=int(merged.get("timeout", 30)),
                depends_on=tuple(merged.get("depends_on", [])),
                profiles=tuple(merged.get("profiles", ["backend"])),
                cwd=merged.get("cwd", "."),
                readiness=bool(merged.get("readiness", False)),
                warmup=merged.get("warmup"),
                env=merged.get("env", {}),
                display_name=str(merged.get("display_name", name)),
                category=str(merged.get("category", "system")),
                provider=merged.get("provider"),
                python=str(python_services.get(name, python_default)),
                startup_priority=int(merged.get("startup_priority", 100)),
                failure_policy=str(merged.get("failure_policy", "abort")),
            )
        capabilities = {
            name: Capability(
                name=name,
                display_name=str(value.get("display_name", name)),
                minimum_level=AvailabilityLevel(value.get("minimum_level", "FULL_READY")),
                required_services=tuple(value.get("required_services", [])),
                optional_services=tuple(value.get("optional_services", [])),
                degraded_without=tuple(value.get("degraded_without", [])),
            )
            for name, value in metadata.get("capabilities", {}).items()
        }
        return cls(services, capabilities)

    def get(self, name: str) -> Service:
        return self.services[name]

    def for_profile(self, profile: str) -> list[Service]:
        selected = {name for name, svc in self.services.items() if profile in svc.profiles}
        pending = list(selected)
        while pending:
            name = pending.pop()
            for dependency in self.services[name].depends_on:
                if dependency not in selected:
                    selected.add(dependency)
                    pending.append(dependency)
        return [self.services[name] for name in self._topological_order() if name in selected]

    def _validate(self) -> None:
        ports: dict[int, str] = {}
        for service in self.services.values():
            if service.port in ports:
                raise ManifestError(f"duplicate port {service.port}")
            ports[service.port] = service.name
            missing = set(service.depends_on) - self.services.keys()
            if missing:
                raise ManifestError(f"{service.name}: missing dependencies {sorted(missing)}")
        self._topological_order()
        for capability in self.capabilities.values():
            missing = (
                set(capability.required_services)
                | set(capability.optional_services)
                | set(capability.degraded_without)
            ) - self.services.keys()
            if missing:
                raise ManifestError(
                    f"{capability.name}: missing capability services {sorted(missing)}"
                )

    def availability(self, states: Mapping[str, str]) -> AvailabilityLevel:
        ready_levels: set[AvailabilityLevel] = set()
        for capability in self.capabilities.values():
            # A failed process is terminal evidence that the capability is not
            # available. Counting it as ready produced false FULL_READY states
            # while GPU-backed services had already exited.
            if all(states.get(name) == "ready" for name in capability.required_services):
                ready_levels.add(capability.minimum_level)
        if AvailabilityLevel.VOICE_READY in ready_levels:
            declared = {
                name
                for capability in self.capabilities.values()
                for name in (
                    capability.required_services
                    + capability.optional_services
                )
            }
            all_declared_ready = all(
                states.get(name) == "ready" for name in declared
            )
            return AvailabilityLevel.FULL_READY if all_declared_ready else AvailabilityLevel.VOICE_READY
        if AvailabilityLevel.TEXT_READY in ready_levels:
            return AvailabilityLevel.TEXT_READY
        return AvailabilityLevel.BLOCKED

    def _topological_order(self) -> list[str]:
        visiting: set[str] = set()
        visited: set[str] = set()
        result: list[str] = []

        def visit(name: str) -> None:
            if name in visiting:
                raise ManifestError("dependency cycle")
            if name in visited:
                return
            visiting.add(name)
            for dependency in self.services[name].depends_on:
                visit(dependency)
            visiting.remove(name)
            visited.add(name)
            result.append(name)

        for name in sorted(
            self.services,
            key=lambda item: (self.services[item].startup_priority, item),
        ):
            visit(name)
        return result
