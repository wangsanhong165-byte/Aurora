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
            with request.urlopen(
                f"http://{service.host}:{service.port}{service.health}", timeout=2
            ) as response:
                if response.status not in (200, 404):
                    return False
                if service.readiness and response.status == 200:
                    import json
                    payload = json.loads(response.read() or b"{}")
                    return payload.get("ready", True) is not False
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
