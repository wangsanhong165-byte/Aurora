from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class Service:
    name: str
    host: str
    port: int
    command: Mapping[str, object]
    health: str | None = None
    timeout: int = 30
    depends_on: tuple[str, ...] = ()
    profiles: tuple[str, ...] = ("backend",)
    cwd: str = "."
    readiness: bool = False
    warmup: Mapping[str, object] | None = None
    env: Mapping[str, str] = field(default_factory=dict)

    def argv(self, root: Path) -> list[str]:
        command = self.command
        executable = (
            str(command.get("executable", "{python}"))
            .replace("{python}", sys.executable)
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


class ServiceManifest:
    def __init__(self, services: dict[str, Service]):
        self.services = services
        self._validate()

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        env: Mapping[str, str] | None = None,
        overrides: Mapping[str, Mapping[str, object]] | None = None,
        cli_overrides: Mapping[str, Mapping[str, object]] | None = None,
    ) -> "ServiceManifest":
        raw = json.loads(path.read_text(encoding="utf-8"))
        environment = env if env is not None else os.environ
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
                health=merged.get("health"),
                timeout=int(merged.get("timeout", 30)),
                depends_on=tuple(merged.get("depends_on", [])),
                profiles=tuple(merged.get("profiles", ["backend"])),
                cwd=merged.get("cwd", "."),
                readiness=bool(merged.get("readiness", False)),
                warmup=merged.get("warmup"),
                env=merged.get("env", {}),
            )
        return cls(services)

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

        for name in self.services:
            visit(name)
        return result
