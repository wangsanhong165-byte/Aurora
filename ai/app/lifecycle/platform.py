from __future__ import annotations

import os
import subprocess
import sys
import ctypes
import socket
from ctypes import wintypes
from pathlib import Path

import psutil

from .registry import ProcessIdentity


class PlatformProcessAdapter:
    def __init__(self):
        self._job = self._create_job() if sys.platform == "win32" else None

    @staticmethod
    def _create_job():
        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class BASIC_LIMIT(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class EXTENDED_LIMIT(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BASIC_LIMIT),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = EXTENDED_LIMIT()
        limits.BasicLimitInformation.LimitFlags = 0x00002000
        if not kernel32.SetInformationJobObject(
            job, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            error = ctypes.get_last_error()
            kernel32.CloseHandle(job)
            raise ctypes.WinError(error)
        return job

    def spawn(self, argv: list[str], cwd: Path, env: dict[str, str], log) -> subprocess.Popen:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        process = subprocess.Popen(
            argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
            stdout=log, stderr=log, creationflags=flags,
        )
        if self._job is not None:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            if not kernel32.AssignProcessToJobObject(self._job, wintypes.HANDLE(process._handle)):
                error = ctypes.get_last_error()
                process.terminate()
                raise ctypes.WinError(error)
        return process

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

    def bind_error(self, host: str, port: int) -> OSError | None:
        """Return the OS bind error before starting a slow model process.

        On Windows, excluded port ranges fail with WinError 10013 without a
        listening owner. Detecting that here avoids waiting for a readiness
        timeout after the child has already exited.
        """
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind((host, port))
        except OSError as exc:
            return exc
        finally:
            probe.close()
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
