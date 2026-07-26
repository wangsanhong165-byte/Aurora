from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import psutil

from .registry import ProcessIdentity


class PlatformProcessAdapter:
    def spawn(self, argv: list[str], cwd: Path, env: dict[str, str], log) -> subprocess.Popen:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        return subprocess.Popen(
            argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
            stdout=log, stderr=log, creationflags=flags,
        )

    def identity(self, pid: int, port: int) -> ProcessIdentity | None:
        try:
            process = psutil.Process(pid)
            return ProcessIdentity(
                pid=pid,
                create_time=process.create_time(),
                executable=process.exe(),
                command=tuple(process.cmdline()),
                port=port,
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None

    def port_owner(self, port: int) -> int | None:
        for connection in psutil.net_connections(kind="inet"):
            if connection.status == psutil.CONN_LISTEN and connection.laddr.port == port:
                return connection.pid
        return None

    def terminate_tree(self, identity: ProcessIdentity) -> bool:
        actual = self.identity(identity.pid, identity.port)
        if actual != identity:
            return False
        try:
            parent = psutil.Process(identity.pid)
            children = parent.children(recursive=True)
            for process in reversed(children):
                process.terminate()
            _gone, alive = psutil.wait_procs(children, timeout=3)
            for process in alive:
                process.kill()
            psutil.wait_procs(alive, timeout=3)
            parent.terminate()
            try:
                parent.wait(timeout=5)
            except psutil.TimeoutExpired:
                parent.kill()
            return True
        except psutil.NoSuchProcess:
            return True
