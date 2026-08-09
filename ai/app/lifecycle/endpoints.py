from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Mapping

from .manifest import Service


@dataclass(frozen=True)
class PortRejection:
    service_id: str
    port: int
    reason: str
    detail: str


@dataclass(frozen=True)
class EndpointPlan:
    services: Mapping[str, Service]
    rejections: tuple[PortRejection, ...]


class EndpointResolutionError(RuntimeError):
    pass


class EndpointResolver:
    """Resolve one bindable endpoint per service before any child is started."""

    def __init__(self, platform):
        self.platform = platform

    def resolve(
        self,
        services: Iterable[Service],
        *,
        pinned_ports: Mapping[str, int] | None = None,
    ) -> EndpointPlan:
        resolved: dict[str, Service] = {}
        rejections: list[PortRejection] = []
        claimed: dict[int, str] = {}
        pinned_ports = pinned_ports or {}

        for service in services:
            if service.name in pinned_ports:
                port = pinned_ports[service.name]
                claimed[port] = service.name
                resolved[service.name] = replace(service, port=port)
                continue
            selected_port: int | None = None
            for port in service.port_candidates:
                if port in claimed:
                    rejections.append(PortRejection(
                        service.name,
                        port,
                        "claimed_by_launch",
                        f"already selected for {claimed[port]}",
                    ))
                    continue

                owner = self.platform.port_owner(port)
                if owner:
                    rejections.append(PortRejection(
                        service.name,
                        port,
                        "occupied",
                        f"occupied by an external or unverified process PID {owner}",
                    ))
                    continue

                bind_error = getattr(
                    self.platform,
                    "bind_error",
                    lambda _host, _port: None,
                )
                error = bind_error(service.host, port)
                if error is not None:
                    code = getattr(error, "winerror", None) or getattr(error, "errno", None)
                    reason = "excluded_or_denied" if code in {13, 10013} else "bind_failed"
                    rejections.append(PortRejection(
                        service.name,
                        port,
                        reason,
                        str(error),
                    ))
                    continue

                selected_port = port
                claimed[port] = service.name
                break

            if selected_port is None and service.dynamic_port:
                try:
                    selected_port = self.platform.allocate_port(service.host, set(claimed))
                    claimed[selected_port] = service.name
                except OSError as exc:
                    rejections.append(PortRejection(
                        service.name,
                        0,
                        "dynamic_allocation_failed",
                        str(exc),
                    ))

            if selected_port is None:
                attempts = ", ".join(str(port) for port in service.port_candidates)
                if service.dynamic_port:
                    attempts += ", OS-assigned"
                details = "; ".join(
                    f"{item.port}: {item.detail}"
                    for item in rejections
                    if item.service_id == service.name
                )
                raise EndpointResolutionError(
                    f"{service.name}: cannot bind {service.host}:{service.port}; "
                    f"no bindable port from [{attempts}]: {details}"
                )
            resolved[service.name] = replace(service, port=selected_port)

        return EndpointPlan(resolved, tuple(rejections))
