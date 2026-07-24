"""Service configuration — single source of truth for all service host/port/URL configs.

Reads from config/services.json. Priority: environment variable > services.json > code default.
Cached after first load. Both Python and Node.js consumers read the same services.json.
"""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Any


_SERVICES_PATH = Path(__file__).resolve().parents[2] / "config" / "services.json"


class ServiceConfig:
    """Singleton service configuration reader.

    Usage:
        from app.config_manager.service_config import service_config
        port = service_config.port("asr")       # 9101
        url  = service_config.url("asr")        # "http://127.0.0.1:9101"
        host = service_config.host("asr")       # "127.0.0.1"
    """

    def __init__(self) -> None:
        self._services: dict[str, dict] | None = None

    # ── public accessors ──────────────────────────────────────────────

    def port(self, name: str) -> int:
        """Return the configured port for *name*, with env-var override."""
        svc = self._get(name)
        env_val = os.environ.get(f"{name.upper()}_PORT")
        if env_val is not None:
            return int(env_val)
        return int(svc["port"])

    def host(self, name: str) -> str:
        """Return the configured host for *name*, with env-var override."""
        svc = self._get(name)
        return os.environ.get(f"{name.upper()}_HOST", svc.get("host", "127.0.0.1"))

    def url(self, name: str) -> str:
        """Return 'http://{host}:{port}' with env-var override."""
        env_url = os.environ.get(f"{name.upper()}_URL")
        if env_url is not None:
            return env_url.rstrip("/")
        return f"http://{self.host(name)}:{self.port(name)}"

    def health_url(self, name: str) -> str | None:
        """Return the health-check URL, or None if the service has none."""
        svc = self._get(name)
        path = svc.get("health")
        if not path:
            return None
        return self.url(name) + path

    def timeout(self, name: str) -> int:
        """Return the startup timeout in seconds."""
        return int(self._get(name).get("timeout", 30))

    def get(self, name: str) -> dict:
        """Return the raw service dict (host, port, health, timeout)."""
        return dict(self._get(name))

    def all_services(self) -> dict[str, dict]:
        """Return the full service map."""
        self._load()
        return dict(self._services or {})

    # ── validation ───────────────────────────────────────────────────

    def get_all(self) -> dict[str, dict]:
        """Return the full service map {name: {host, port, ...}}."""
        self._load()
        return dict(self._services or {})

    def all_ports(self) -> set[int]:
        """Return the set of all configured service ports."""
        self._load()
        return {int(svc["port"]) for svc in (self._services or {}).values()}

    def validate(self) -> list[str]:
        """Check all ports are bindable and non-conflicting.

        Returns a list of error messages (empty = all OK).
        """
        self._load()
        errors: list[str] = []
        seen_ports: dict[int, list[str]] = {}

        for name, svc in (self._services or {}).items():
            port = int(svc["port"])
            seen_ports.setdefault(port, []).append(name)

            # Check port is actually free
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.3)
                s.bind((svc.get("host", "127.0.0.1"), port))
                s.close()
            except OSError as exc:
                errors.append(f"[{name}] port {port} unavailable: {exc}")

        # Check for port conflicts
        for port, names in seen_ports.items():
            if len(names) > 1:
                errors.append(
                    f"Port {port} is shared by: {', '.join(names)}"
                )

        return errors

    # ── internal ─────────────────────────────────────────────────────

    def _get(self, name: str) -> dict:
        self._load()
        svc = (self._services or {}).get(name)
        if svc is None:
            msg = f"Unknown service '{name}'. Known: {list(self._services or [])}"
            raise KeyError(msg)
        return svc

    def _load(self) -> None:
        if self._services is not None:
            return
        if not _SERVICES_PATH.exists():
            self._services = {}
            return
        raw = json.loads(_SERVICES_PATH.read_text(encoding="utf-8"))
        # Strip _meta key if present
        self._services = {k: v for k, v in raw.items() if not k.startswith("_")}


# Module-level singleton (cached after first import)
service_config = ServiceConfig()
