#!/usr/bin/env python
"""Companion Runtime Lifecycle Manager — unified dev environment control.

Usage:
    python scripts/lifecycle.py start          Start full development environment
    python scripts/lifecycle.py start --web    Start backend + bridge only (no Vite)
    python scripts/lifecycle.py start --mode electron  Start backend + Electron
    python scripts/lifecycle.py stop           Stop all managed services
    python scripts/lifecycle.py restart        Safe restart
    python scripts/lifecycle.py status         Show running services
    python scripts/lifecycle.py clean          Clean caches and artifacts
    python scripts/lifecycle.py logs           Tail all logs
    python scripts/lifecycle.py logs --service bridge  Tail specific service logs

PID tracking: data/pids/processes.json
Logs:          logs/<service>.log
"""

from __future__ import annotations

import argparse
import io
import json
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Force UTF-8 on Windows ──────────────────────────────────────────────
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Paths ───────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

PIDS_DIR = BASE_DIR / "data" / "pids"
LOGS_DIR = BASE_DIR / "logs"
PID_FILE = PIDS_DIR / "processes.json"

from app.config_manager.service_config import service_config

_SVC = service_config  # shorthand


def _svc_cmd(name: str, *extra_args: str) -> list[str]:
    """Build a service command list from service_config."""
    cmd = [sys.executable, "-m", f"app.modules.{name}.api",
           "--host", _SVC.host(name), "--port", str(_SVC.port(name))]
    cmd.extend(extra_args)
    return cmd


# ── Service definitions ─────────────────────────────────────────────────
# All ports come from config/services.json. Set env var NAME_PORT to override.

SERVICES: list[dict[str, Any]] = [
    {
        "name": "tts",
        "cmd": _svc_cmd("tts", "--env-file", str(BASE_DIR / "config" / ".env")),
        "port": _SVC.port("tts"),
        "timeout": _SVC.timeout("tts"),
        "health_url": _SVC.health_url("tts"),
        "description": "TTS (text-to-speech) — starts first for GPU allocation",
    },
    {
        "name": "asr",
        "cmd": _svc_cmd("asr"),
        "port": _SVC.port("asr"),
        "timeout": _SVC.timeout("asr"),
        "health_url": _SVC.health_url("asr"),
        "description": "ASR (speech recognition)",
    },
    {
        "name": "llm",
        "cmd": _svc_cmd("llm", "--env-file", str(BASE_DIR / "config" / ".env")),
        "port": _SVC.port("llm"),
        "timeout": _SVC.timeout("llm"),
        "health_url": _SVC.health_url("llm"),
        "description": "LLM (language model)",
    },
    {
        "name": "memory",
        "cmd": _svc_cmd("memory"),
        "port": _SVC.port("memory"),
        "timeout": _SVC.timeout("memory"),
        "health_url": _SVC.health_url("memory"),
        "description": "Memory service",
    },
    {
        "name": "bridge",
        "cmd": [sys.executable, "-m", "app.bridge.server"],
        "port": _SVC.port("bridge"),
        "timeout": _SVC.timeout("bridge"),
        "health_url": None,  # bridge port check only
        "description": "Live2D Bridge + WS server",
    },
]

GSVI_SERVICE: dict[str, Any] = {
    "name": "gsvi",
    "port": _SVC.port("gsvi"),
    "timeout": _SVC.timeout("gsvi"),
    "health_url": _SVC.health_url("gsvi"),
    "description": "GSVI v2Pro TTS engine",
}

FRONTEND_SERVICE: dict[str, Any] = {
    "name": "frontend",
    "port": _SVC.port("frontend"),
    "description": "Vite dev server",
}


# ── Utilities ───────────────────────────────────────────────────────────

def _load_env() -> None:
    """Load .env if not already loaded."""
    if os.environ.get("_LIFECYCLE_ENV_LOADED"):
        return
    try:
        from app.core.config import DEFAULT_ENV_PATH, load_env_file
        load_env_file(DEFAULT_ENV_PATH)
        os.environ["_LIFECYCLE_ENV_LOADED"] = "1"
    except ImportError:
        pass


def _port_in_use(port: int) -> bool:
    """Check if a TCP port is in use on 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True


def _find_pid_on_port(port: int) -> int | None:
    """Find the PID of a process listening on a given port."""
    try:
        import psutil
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr and conn.laddr.port == port and conn.status == "LISTEN":
                return conn.pid
    except Exception:
        pass
    return None


def _read_pid_file() -> dict[str, Any]:
    """Read PID tracking file; returns dict or empty dict."""
    if PID_FILE.exists():
        try:
            return json.loads(PID_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _write_pid_file(data: dict[str, Any]) -> None:
    """Write PID tracking file atomically."""
    PIDS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = PID_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(PID_FILE)


def _log_path(name: str) -> Path:
    """Return the log file path for a service."""
    return LOGS_DIR / f"{name}.log"


def _ensure_log_dir() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _stamp() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _is_pid_alive(pid: int) -> bool:
    """Check if a PID is still running."""
    try:
        import psutil
        return psutil.pid_exists(pid) and psutil.Process(pid).is_running()
    except Exception:
        pass
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False
    except PermissionError:
        return True  # exists but owned by another user


# ── Process management ──────────────────────────────────────────────────

def start_service(svc: dict[str, Any], env: dict[str, str] | None = None) -> subprocess.Popen | None:
    """Start a single service and return the Popen object."""
    name = svc["name"]
    port = svc.get("port")

    # Check port availability
    if port and _port_in_use(port):
        pid = _find_pid_on_port(port)
        existing = f" (PID {pid})" if pid else ""
        print(f"  ⚠  {name} port {port} already in use{existing}, skipping")
        # Still record it if we found a PID
        if pid:
            return None
        return None

    # Build environment
    child_env = os.environ.copy()
    child_env.setdefault("PYTHONIOENCODING", "utf-8")
    child_env.setdefault("PYTHONUTF8", "1")
    child_env["PYTHONDONTWRITEBYTECODE"] = "1"
    if env:
        child_env.update(env)

    _ensure_log_dir()
    log_path = _log_path(name)
    log_file = open(log_path, "a", encoding="utf-8")

    # Log header
    log_file.write(f"\n{'='*60}\n")
    log_file.write(f"=== Started at {_stamp()}\n")
    log_file.write(f"=== {' '.join(svc['cmd'])}\n")
    log_file.write(f"{'='*60}\n")
    log_file.flush()

    print(f"  ▶  Starting {name} on port {port} ...", end="", flush=True)
    try:
        proc = subprocess.Popen(
            svc["cmd"],
            cwd=BASE_DIR,
            env=child_env,
            stdout=log_file,
            stderr=log_file,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
        print(f" PID {proc.pid}")
        return proc
    except Exception as e:
        print(f" FAILED: {e}")
        log_file.write(f"FAILED: {e}\n")
        log_file.close()
        return None


def start_gsvi(env: dict[str, str] | None = None) -> subprocess.Popen | None:
    """Start GSVI v2Pro TTS engine (special — different python env)."""
    from app.core.config import DEFAULT_ENV_PATH, load_env_file
    load_env_file(DEFAULT_ENV_PATH)

    gsvi_dir = BASE_DIR / "models" / "tts" / "GPT-SoVITS-v2pro-20250604-nvidia50"
    gsvi_python = gsvi_dir / "runtime" / "python.exe"
    gsvi_config = gsvi_dir / "GPT_SoVITS" / "configs" / "tts_infer.yaml"

    if not gsvi_dir.exists():
        print(f"  ⚠  GSVI v2Pro directory not found: {gsvi_dir}")
        return None
    if not gsvi_python.exists():
        print(f"  ⚠  GSVI python not found: {gsvi_python}")
        return None

    cmd = [str(gsvi_python), str(gsvi_dir / "api_v2.py"),
           "-a", _SVC.host("gsvi"), "-p", str(_SVC.port("gsvi")), "-c", str(gsvi_config)]

    child_env = os.environ.copy()
    child_env["PATH"] = f"{gsvi_dir / 'runtime'};{child_env.get('PATH', '')}"
    child_env["BROWSER"] = "none"
    child_env["PYTHONDONTWRITEBYTECODE"] = "1"
    if env:
        child_env.update(env)

    _ensure_log_dir()
    log_path = _log_path("gsvi")
    log_file = open(log_path, "a", encoding="utf-8")
    log_file.write(f"\n{'='*60}\n=== GSVI started at {_stamp()}\n{'='*60}\n")
    log_file.flush()

    print(f"  ▶  Starting GSVI v2Pro on port {_SVC.port('gsvi')} ...", end="", flush=True)
    try:
        proc = subprocess.Popen(
            cmd, cwd=gsvi_dir, env=child_env,
            stdout=log_file, stderr=log_file,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
        print(f" PID {proc.pid}")
        return proc
    except Exception as e:
        print(f" FAILED: {e}")
        log_file.write(f"FAILED: {e}\n")
        log_file.close()
        return None


def start_frontend(env: dict[str, str] | None = None) -> subprocess.Popen | None:
    """Start Vite dev server."""
    fp = _SVC.port("frontend")
    if _port_in_use(fp):
        pid = _find_pid_on_port(fp)
        existing = f" (PID {pid})" if pid else ""
        print(f"  ⚠  Frontend port {fp} already in use{existing}, skipping")
        return None

    frontend_dir = BASE_DIR / "frontend"
    if not (frontend_dir / "package.json").exists():
        print(f"  ⚠  Frontend directory invalid: {frontend_dir}")
        return None

    child_env = os.environ.copy()
    if env:
        child_env.update(env)

    _ensure_log_dir()
    log_path = _log_path("frontend")
    log_file = open(log_path, "a", encoding="utf-8")
    log_file.write(f"\n{'='*60}\n=== Frontend started at {_stamp()}\n{'='*60}\n")
    log_file.flush()

    print(f"  ▶  Starting Vite dev server on port {_SVC.port('frontend')} ...", end="", flush=True)
    try:
        npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
        proc = subprocess.Popen(
            [npm_cmd, "run", "dev"],
            cwd=frontend_dir,
            env=child_env,
            stdout=log_file,
            stderr=log_file,
            shell=(sys.platform == "win32"),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
        print(f" PID {proc.pid}")
        return proc
    except Exception as e:
        print(f" FAILED: {e}")
        log_file.write(f"FAILED: {e}\n")
        log_file.close()
        return None


def wait_for_port(port: int, timeout: float = 30.0) -> bool:
    """Wait until a TCP port is accepting connections."""
    start = time.time()
    while time.time() - start < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            try:
                s.connect(("127.0.0.1", port))
                return True
            except (ConnectionRefusedError, OSError, TimeoutError):
                pass
        time.sleep(0.3)
    return False


def wait_for_health(
    url: str,
    timeout: float = 30.0,
    *,
    require_ready: bool = False,
) -> bool:
    """Wait for HTTP health and optionally require a JSON ready=true state."""
    import json
    import urllib.request

    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status not in (200, 404):
                    continue
                if require_ready and response.status == 200:
                    payload = json.loads(response.read().decode("utf-8"))
                    model_ready = (
                        payload.get("ready") is True
                        or payload.get("models_loaded") is True
                        or payload.get("status") == "ready"
                    )
                    if not model_ready:
                        time.sleep(0.5)
                        continue
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def warmup_tts(timeout: float = 180.0) -> bool:
    """Trigger real TTS inference after GSVI reports ready."""
    import urllib.request

    url = f"{_SVC.url('tts')}/warmup"
    request = urllib.request.Request(
        url,
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status == 200
    except Exception as exc:
        print(f"  [FAIL] tts warmup: {exc}")
        return False


# ── Signal handling ─────────────────────────────────────────────────────

_shutdown_flag = False


def _handle_signal(signum, frame) -> None:
    global _shutdown_flag
    _shutdown_flag = True


# ── Command implementations ─────────────────────────────────────────────

def cmd_start(args: argparse.Namespace) -> int:
    """Start development environment."""
    _load_env()
    procs: dict[str, subprocess.Popen | None] = {}

    # Check for existing managed processes
    existing = _read_pid_file()
    stale_entries = []
    for name, info in existing.items():
        pid = info.get("pid")
        if pid and _is_pid_alive(pid):
            print(f"  ⚠  {name} (PID {pid}) already running, stopping first...")
            _stop_service(name, info)
            stale_entries.append(name)
        elif pid:
            stale_entries.append(name)

    # Remove stale entries
    for name in stale_entries:
        existing.pop(name, None)
    if stale_entries:
        _write_pid_file(existing)

    mode = args.mode
    electron_mode = mode == "electron"

    # Determine what to start
    do_backend = mode in ("full", "backend", "electron") and not args.no_backend
    do_bridge = mode in ("full", "web", "backend", "electron") and not args.no_backend
    do_frontend = mode in ("full", "web", "electron") and not args.no_frontend

    start_time = time.time()

    print(f"\n{'='*50}")
    print(f"  Companion Runtime — Starting ({mode} mode)")
    print(f"  {_stamp()}")
    print(f"{'='*50}\n")

    # ── 1. GSVI v2Pro (TTS GPU engine — must start first for GPU allocation) ──
    gsvi_enabled = os.environ.get("START_GSVI", "true").strip().lower() in ("1", "true", "yes", "on")
    if gsvi_enabled and do_backend:
        print("── TTS Engine (GPU) ──")
        gsvi_proc = start_gsvi()
        if gsvi_proc:
            procs["gsvi"] = gsvi_proc
            print(f"     waiting up to {GSVI_SERVICE['timeout']}s ...", end="", flush=True)
            ready = wait_for_health(
                _SVC.health_url("gsvi"),
                GSVI_SERVICE["timeout"],
                require_ready=True,
            )
            if ready:
                print(f" ✓  ({time.time() - start_time:.1f}s)")
            else:
                print(" ✗ (timeout)")
        else:
            print("     (skipped)")

    # ── 2. Backend services (TTS first for GPU, then ASR, LLM, Memory) ──
    if do_backend:
        print("── Backend services (ordered GPU preload) ──")
        by_name = {svc["name"]: svc for svc in SERVICES}

        tts_svc = by_name["tts"]
        procs["tts"] = start_service(tts_svc)
        tts_ready = bool(procs["tts"]) and wait_for_health(
            tts_svc["health_url"],
            tts_svc["timeout"],
            require_ready=True,
        )
        if tts_ready:
            print("  ... TTS adapter ready; warming GSVI inference")
            tts_ready = warmup_tts(tts_svc["timeout"])
        print(f"  {'✓' if tts_ready else '✗'} tts warm")

        asr_svc = by_name["asr"]
        procs["asr"] = start_service(asr_svc)
        asr_ready = bool(procs["asr"]) and wait_for_health(
            asr_svc["health_url"],
            asr_svc["timeout"],
            require_ready=True,
        )
        print(f"  {'✓' if asr_ready else '✗'} asr model resident")

        for name in ("llm", "memory"):
            svc = by_name[name]
            procs[name] = start_service(svc)
            service_ready = bool(procs[name]) and wait_for_health(
                svc["health_url"],
                svc["timeout"],
            )
            print(f"  {'✓' if service_ready else '✗'} {name}")

    # ── 2. Bridge (always in any mode) ──
    if do_bridge:
        print()
        print("── Transport ──")
        bridge_svc = next(s for s in SERVICES if s["name"] == "bridge")
        procs["bridge"] = start_service(bridge_svc)
        if procs["bridge"]:
            ready = wait_for_port(_SVC.port("bridge"), 15)
            elapsed = time.time() - start_time
            if ready:
                print(f"  ✓  bridge ready  ({elapsed:.1f}s)")
            else:
                print(f"  ✗  bridge NOT ready  ({elapsed:.1f}s)")

        # Save PIDs
        pid_data = _read_pid_file()
        for name, proc in procs.items():
            if proc and proc.pid:
                svc_info = next((s for s in SERVICES if s["name"] == name), None)
                pid_data[name] = {
                    "pid": proc.pid,
                    "port": svc_info["port"] if svc_info else 0,
                    "started_at": _stamp(),
                }
        if "gsvi" in procs and procs["gsvi"] and procs["gsvi"].pid:
            pid_data["gsvi"] = {
                "pid": procs["gsvi"].pid,
                "port": _SVC.port("gsvi"),
                "started_at": _stamp(),
            }
        _write_pid_file(pid_data)

    # ── 3. Frontend (Vite dev server) ──
    if do_frontend:
        print()
        print("── Frontend ──")
        frontend_proc = start_frontend()
        if frontend_proc:
            procs["frontend"] = frontend_proc
            ready = wait_for_port(_SVC.port("frontend"), 15)
            if ready:
                print(f"  ✓  frontend ready  ({time.time() - start_time:.1f}s)")
            # Save PID
            pid_data = _read_pid_file()
            pid_data["frontend"] = {
                "pid": frontend_proc.pid,
                "port": _SVC.port("frontend"),
                "started_at": _stamp(),
            }
            _write_pid_file(pid_data)
        print()
        print("── Electron ──")
        try:
            npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
            electron_proc = subprocess.Popen(
                [npm_cmd, "run", "electron:start"],
                cwd=BASE_DIR / "frontend",
                env=os.environ.copy(),
                shell=(sys.platform == "win32"),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            )
            procs["electron"] = electron_proc
            pid_data = _read_pid_file()
            pid_data["electron"] = {
                "pid": electron_proc.pid,
                "port": 0,
                "started_at": _stamp(),
            }
            _write_pid_file(pid_data)
            print(f"  ▶  Electron started (PID {electron_proc.pid})")
        except Exception as e:
            print(f"  ✗  Electron failed: {e}")

    # ── Summary ──
    elapsed = time.time() - start_time
    print()
    print(f"{'='*50}")
    print(f"  Summary ({elapsed:.1f}s)")
    print(f"{'='*50}")
    print(f"  Backend API:  http://127.0.0.1:{_SVC.port('bridge')}")
    print(f"  Frontend:     http://127.0.0.1:{_SVC.port('frontend')}")
    for name, proc in procs.items():
        if proc and proc.pid:
            try:
                alive = _is_pid_alive(proc.pid)
                status = "RUNNING" if alive else "DIED"
            except Exception:
                status = "?"
            print(f"  {name:12s} PID {proc.pid}  [{status}]")
    print()

    if do_frontend and do_bridge:
        print(f"  Open http://127.0.0.1:{_SVC.port('frontend')} in your browser")
    elif do_bridge:
        print(f"  Open http://127.0.0.1:{_SVC.port('bridge')} in your browser")
    print()

    # ── Block until Ctrl+C ──
    if do_bridge or do_backend:
        print("  Press Ctrl+C to stop all services")
        print()

        # Register signal handlers
        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        try:
            while not _shutdown_flag:
                time.sleep(0.5)
                # Check that critical processes are still alive
                for name, proc in list(procs.items()):
                    if proc is None:
                        continue
                    if name in ("frontend", "electron"):
                        continue  # can be restarted independently
                    if proc.poll() is not None:
                        print(f"  ⚠  {name} (PID {proc.pid}) exited unexpectedly")
                        procs.pop(name, None)
        except KeyboardInterrupt:
            pass
        finally:
            print("\nShutting down...")
            cmd_stop(args)

    return 0


def _stop_service(name: str, info: dict[str, Any]) -> bool:
    """Stop a single service by PID."""
    pid = info.get("pid")
    port = info.get("port", 0)
    if not pid:
        return False

    try:
        import psutil
        try:
            proc = psutil.Process(pid)
            proc_name = proc.name()

            # Check if this process belongs to our project
            cmdline = proc.cmdline()
            cmd_str = " ".join(cmdline).lower()
            is_ours = any(term in cmd_str for term in [
                "app.modules", "app.bridge", "run_bridge", "companion",
                "npm run dev", "npm.cmd run dev", "electron", "api_v2.py",
            ])

            if not is_ours and port:
                is_ours = True  # Assume it's ours if tracked by our PID file

            if not is_ours:
                print(f"  ⚠  {name} PID {pid} doesn't appear to be a project process, skipping")
                return False

            # Terminate the entire process tree (handles shell=True children on Windows)
            print(f"  ■  Stopping {name} (PID {pid}) ...", end="", flush=True)
            children = proc.children(recursive=True)
            for child in children:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
            # Give children time to exit
            gone, alive = psutil.wait_procs(children, timeout=3)
            for child in alive:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass

            # Now terminate the parent
            proc.terminate()
            try:
                proc.wait(timeout=5)
                print(" done")
            except (psutil.TimeoutExpired, subprocess.TimeoutExpired):
                proc.kill()
                print(" force killed")
            return True

        except psutil.NoSuchProcess:
            print(f"  -  {name} (PID {pid}) already gone")
            return True
    except ImportError:
        # Fallback when psutil is not available
        try:
            print(f"  ■  Stopping {name} (PID {pid}) ...", end="", flush=True)
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
            else:
                os.kill(pid, signal.SIGTERM)
            print(" done")
            return True
        except Exception as e:
            print(f" error: {e}")
            return False


def cmd_stop(args: argparse.Namespace) -> int:
    """Stop all managed services."""
    pid_data = _read_pid_file()
    if not pid_data:
        print("No managed processes found.")
        # Fallback: check common ports
        return _stop_by_ports()

    # Stop in reverse order (frontend first, then bridge, then services)
    stop_order = ["electron", "frontend", "bridge", "gsvi", "tts", "asr", "llm", "memory"]

    print(f"\n{'='*50}")
    print("  Stopping all services")
    print(f"{'='*50}\n")

    for name in stop_order:
        if name in pid_data:
            _stop_service(name, pid_data[name])

    _write_pid_file({})

    # Confirm ports are released
    print()
    print("── Port check ──")
    all_ports = list(_SVC.all_ports())
    for port in all_ports:
        if _port_in_use(port):
            pid = _find_pid_on_port(port)
            if pid:
                try:
                    import psutil
                    p = psutil.Process(pid)
                    cmd = " ".join(p.cmdline())[:80]
                    print(f"  ⚠  Port {port} still in use (PID {pid}: {cmd})")
                except Exception:
                    print(f"  ⚠  Port {port} still in use (PID {pid})")
        else:
            print(f"  ✓  Port {port} free")

    return 0


def _stop_by_ports() -> int:
    """Fallback: stop processes by checking project ports."""
    print("Scanning project ports for orphan processes...")
    project_ports = list(_SVC.all_ports())
    found = False
    for port in project_ports:
        pid = _find_pid_on_port(port)
        if pid:
            try:
                import psutil
                p = psutil.Process(pid)
                cmd = " ".join(p.cmdline())[:100]
                print(f"  Found PID {pid} on port {port}: {cmd}")
                p.terminate()
                try:
                    p.wait(timeout=3)
                    print(f"  Stopped PID {pid}")
                except Exception:
                    p.kill()
                    print(f"  Force killed PID {pid}")
                found = True
            except Exception as e:
                print(f"  Error stopping PID {pid}: {e}")
    if not found:
        print("  No orphan processes found")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Show status of all managed services."""
    pid_data = _read_pid_file()

    print(f"\n{'='*50}")
    print(f"  Companion Runtime — Status ({_stamp()})")
    print(f"{'='*50}")

    # Managed processes
    print(f"\n── Managed processes ──")
    if pid_data:
        for name, info in pid_data.items():
            pid = info.get("pid")
            port = info.get("port", 0)
            alive = _is_pid_alive(pid) if pid else False
            status = "● RUNNING" if alive else "○ STOPPED"
            port_str = f" :{port}" if port else ""
            print(f"  {name:12s} PID {pid or '-':<6} {port_str:8s} {status}")
    else:
        print("  (none tracked)")
        # Check ports anyway
        print()

    # Port scan
    print("── Port scan ──")
    all_services = [
        (name.upper(), svc["port"])
        for name, svc in sorted(_SVC.get_all().items())
    ]
    for name, port in all_services:
        in_use = _port_in_use(port)
        pid = _find_pid_on_port(port) if in_use else None
        status = "●" if in_use else "○"
        pid_str = f" PID {pid}" if pid else ""
        print(f"  {status} {name:10s} :{port}  {pid_str}")

    # Log file sizes
    print(f"\n── Logs ──")
    any_logs = False
    for name, _ in all_services:
        log_path = _log_path(name.lower())
        if log_path.exists():
            size = log_path.stat().st_size
            print(f"  {name:10s} {_format_size(size):>8s}  {log_path.name}")
            any_logs = True
    if not any_logs:
        print(f"  (no log files yet — run `start` to generate logs)")
    print()
    return 0


def _format_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def cmd_clean(args: argparse.Namespace) -> int:
    """Clean caches and build artifacts."""
    print(f"\n{'='*50}")
    print("  Cleaning caches and artifacts")
    print(f"{'='*50}\n")

    # 1. Python __pycache__
    import glob as glob_mod
    pycache_dirs = glob_mod.glob(str(BASE_DIR / "**" / "__pycache__"), recursive=True)
    pycache_count = 0
    for d in pycache_dirs:
        try:
            import shutil
            shutil.rmtree(d)
            pycache_count += 1
        except Exception as e:
            print(f"  ⚠  Could not remove {d}: {e}")
    print(f"  ✓  Removed {pycache_count} __pycache__ directories")

    # 2. .pyc files
    pyc_files = glob_mod.glob(str(BASE_DIR / "**" / "*.pyc"), recursive=True)
    for f in pyc_files:
        try:
            os.remove(f)
        except Exception:
            pass
    print(f"  ✓  Removed {len(pyc_files)} .pyc files")

    # 3. .pytest_cache
    pytest_cache = BASE_DIR / ".pytest_cache"
    if pytest_cache.exists():
        import shutil
        shutil.rmtree(pytest_cache)
        print(f"  ✓  Removed .pytest_cache")

    # 4. Frontend build/dist
    frontend_dist = BASE_DIR / "frontend" / "dist"
    if frontend_dist.exists():
        import shutil
        shutil.rmtree(frontend_dist)
        print(f"  ✓  Removed frontend/dist")

    # 5. Frontend Vite cache (.vite)
    vite_cache = BASE_DIR / "frontend" / "node_modules" / ".vite"
    if vite_cache.exists():
        import shutil
        shutil.rmtree(vite_cache)
        print(f"  ✓  Removed frontend Vite cache")

    # 6. Frontend node_modules (only with --all)
    if args.all:
        node_modules = BASE_DIR / "frontend" / "node_modules"
        if node_modules.exists():
            import shutil
            shutil.rmtree(node_modules)
            print(f"  ✓  Removed frontend/node_modules")

    # 7. Temporary files
    for pattern in ["*.tmp", "*.log.*", "*.pid"]:
        for f in glob_mod.glob(str(BASE_DIR / "**" / pattern), recursive=True):
            try:
                os.remove(f)
            except Exception:
                pass

    # 8. Clean old logs (keep latest 5 per service)
    log_files: dict[str, list[Path]] = {}
    for f in LOGS_DIR.glob("*.log"):
        log_files.setdefault(f.stem.replace(".log", ""), []).append(f)
    for name, files in log_files.items():
        if len(files) > 1:
            files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            for f in files[5:]:
                try:
                    f.unlink()
                    print(f"  ✓  Pruned old log: {f.name}")
                except Exception:
                    pass

    print(f"\n  Done.")
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    """Tail service logs."""
    service = args.service

    if service:
        log_path = _log_path(service)
        if not log_path.exists():
            print(f"No log file for '{service}' at {log_path}")
            return 1
        _tail_log(log_path, args.lines)
    else:
        # Tail all logs
        log_files = sorted(LOGS_DIR.glob("*.log"))
        if not log_files:
            print("No log files found.")
            return 1
        for log_path in log_files:
            print(f"\n── {log_path.name} ──")
            _tail_log(log_path, args.lines)

    return 0


def _tail_log(path: Path, lines: int = 20) -> None:
    """Print the last N lines of a file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        all_lines = text.splitlines()
        for line in all_lines[-lines:]:
            print(f"  {line}")
    except Exception as e:
        print(f"  (error reading log: {e})")


def cmd_restart(args: argparse.Namespace) -> int:
    """Restart all services."""
    print("Restarting all services...")
    cmd_stop(args)
    print()
    # Small delay to let ports release
    time.sleep(2)
    return cmd_start(args)


# ── Argument parser ─────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="companion",
        description="Companion Runtime Lifecycle Manager",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # start
    sp = sub.add_parser("start", help="Start development environment")
    sp.add_argument("--mode", choices=["full", "web", "electron", "backend"],
                    default="full",
                    help="Start mode (default: full = backend + frontend)")
    sp.add_argument("--no-backend", action="store_true",
                    help="Skip backend services (start frontend only)")
    sp.add_argument("--no-frontend", action="store_true",
                    help="Skip frontend (start backend only)")

    # stop
    sub.add_parser("stop", help="Stop all services")

    # restart
    sp = sub.add_parser("restart", help="Restart all services")
    sp.add_argument("--mode", choices=["full", "web", "electron", "backend"],
                    default="full")

    # status
    sub.add_parser("status", help="Show service status")

    # clean
    sp = sub.add_parser("clean", help="Clean caches and artifacts")
    sp.add_argument("--all", action="store_true",
                    help="Also clean node_modules")

    # logs
    sp = sub.add_parser("logs", help="Show service logs")
    sp.add_argument("--service", "-s", default="",
                    help="Service name (e.g. bridge, tts, frontend)")
    sp.add_argument("--lines", "-n", type=int, default=30,
                    help="Number of lines to show (default: 30)")

    return p


# ── Entry point ─────────────────────────────────────────────────────────

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "start":
        return cmd_start(args)
    elif args.command == "stop":
        return cmd_stop(args)
    elif args.command == "restart":
        return cmd_restart(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "clean":
        return cmd_clean(args)
    elif args.command == "logs":
        return cmd_logs(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
