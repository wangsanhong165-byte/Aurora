from __future__ import annotations

import socket
import time
from urllib import request

from .manifest import Service


class HealthProbe:
    def ready(self, service: Service) -> bool:
        if not service.health:
            try:
                with socket.create_connection((service.host, service.port), timeout=1):
                    return True
            except OSError:
                return False
        try:
            # Loopback probes must not be routed through a desktop HTTP proxy.
            _opener = request.build_opener(request.ProxyHandler({}))
            with _opener.open(
                f"http://{service.host}:{service.port}{service.health}", timeout=2
            ) as response:
                if response.status != 200:
                    return False
                if service.readiness:
                    import json
                    payload = json.loads(response.read() or b"{}")
                    if "ready" in payload:
                        return payload.get("ready", True) is not False
                    # GSVI /ready returns {"status": "ready"|"degraded", ...}
                    # with no "ready" key; honor it so a not-yet-loaded model
                    # is NOT reported as ready.
                    return payload.get("status", "ready") != "degraded"
                return True
        except Exception:
            return False

    def wait(self, service: Service, process=None) -> bool:
        deadline = time.monotonic() + service.timeout
        while time.monotonic() < deadline:
            if process is not None and process.poll() is not None:
                return False
            if self.ready(service):
                return True
            time.sleep(0.5)
        return False
