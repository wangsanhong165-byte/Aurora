"""
One-click launcher: start all services, wait for readiness, then enter VAD mode.

Usage:
    python run.py

Options:
    python run.py --no-vad          Single-turn mode instead of continuous
    python run.py --loop            Manual Enter-between-turns mode
    python run.py --tts-voice 角色名   Override GSVI voice
    python run.py --help            Show all options
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from app.core.config import (
    DEFAULT_ENV_PATH,
    GSVI_CONFIG_PATH,
    GSVI_DIR,
    GSVI_HEADLESS,
    GSVI_PYTHON,
    load_env_file,
)

# ── Service definitions ──
SERVICES = [
    ("gsvi",     None,                      "8050", True),
    ("recorder", "app.modules.recorder.api", "8010", False),
    ("asr",      "app.modules.asr.api",      "8000", False),
    ("llm",      "app.modules.llm.api",      "8020", False),
    ("tts",      "app.modules.tts.api",      "8030", False),
    ("memory",   "app.modules.memory.api",   "8040", False),
]

HEALTH_TIMEOUTS = {
    "gsvi": 120.0,    # model loading can take a while
    "asr":  60.0,     # Qwen3-ASR model load
    "llm":  10.0,
}


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def start_service(name: str, module: str | None, port: str, is_gsvi: bool, env_file: str) -> subprocess.Popen | None:
    """Start one service process. Returns Popen or None if skipped."""
    if is_gsvi:
        should = env_bool("START_GSVI", True) or os.environ.get("TTS_ENGINE", "gsvi").lower() == "gsvi"
        if not should:
            print(f"  [skip] gsvi (START_GSVI=false)")
            return None

        if not GSVI_PYTHON.exists():
            print(f"  [skip] gsvi (runtime not found: {GSVI_PYTHON})")
            return None

        command = [
            str(GSVI_PYTHON),
            str(GSVI_HEADLESS),
            "-s", "127.0.0.1",
            "-p", port,
            "-c", str(GSVI_CONFIG_PATH),
        ]
        env = os.environ.copy()
        env["PATH"] = f"{GSVI_DIR / 'runtime'};{env.get('PATH', '')}"
        proc = subprocess.Popen(command, cwd=GSVI_DIR, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        command = [sys.executable, "-m", module]
        if module in {"app.modules.llm.api", "app.modules.tts.api"}:
            command.extend(["--env-file", env_file])
        command.extend(["--host", "127.0.0.1", "--port", port])
        proc = subprocess.Popen(command, cwd=BASE_DIR,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return proc


def wait_for_health(name: str, port: str) -> tuple[bool, float]:
    """Poll /health until ready. Returns (ok, elapsed_seconds)."""
    timeout = HEALTH_TIMEOUTS.get(name, 15.0)
    url = f"http://127.0.0.1:{port}/health"
    start = time.time()
    interval = 0.5

    while time.time() - start < timeout:
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                return True, time.time() - start
        except requests.RequestException:
            pass
        time.sleep(interval)

    return False, time.time() - start


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="One-click voice assistant launcher")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH))
    parser.add_argument("--no-vad", action="store_true", help="Single-turn instead of VAD continuous")
    parser.add_argument("--loop", action="store_true", help="Manual Enter-between-turns mode")
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--memory-limit", type=int, default=8)
    parser.add_argument("--no-tts", action="store_true")
    parser.add_argument("--turns", type=int, default=0)
    parser.add_argument("--tts-engine", choices=["gsvi", "pyttsx3"])
    parser.add_argument("--tts-voice")
    parser.add_argument("--tts-emotion")
    parser.add_argument("--tts-speed", type=float)
    parser.add_argument("--vad-silence-timeout", type=float, default=1.5)
    parser.add_argument("--vad-max-duration", type=float, default=30.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_env_file(Path(args.env_file))
    os.environ.setdefault("GSVI_PORT", "8050")
    os.environ.setdefault("GSVI_URL", "http://127.0.0.1:8050")

    processes: list[tuple[str, subprocess.Popen | None]] = []

    # ── Phase 1: Start all services ──
    print("\nStarting services...")
    for name, module, port, is_gsvi in SERVICES:
        proc = start_service(name, module, port, is_gsvi, str(args.env_file))
        processes.append((name, proc))
        status = "started" if proc else "skipped"
        print(f"  [{status}] {name} → :{port}")

    # ── Phase 2: Wait for readiness ──
    print("\nWaiting for services to be ready...")
    all_ok = True
    for name, proc in processes:
        if proc is None:
            continue
        port = next((s[2] for s in SERVICES if s[0] == name), None)
        ok, elapsed = wait_for_health(name, port or "")
        if ok:
            print(f"  [ok] {name} ready ({elapsed:.1f}s)")
        else:
            print(f"  [FAIL] {name} did not respond in time")
            all_ok = False

    if not all_ok:
        print("\nSome services failed to start. Shutting down...")
        for _, proc in processes:
            if proc:
                proc.terminate()
        return 1

    # ── Phase 3: Ready ──
    print("\n" + "=" * 48)
    print("  All services ready — listening now")
    print("  Speak to interact. Ctrl+C to stop.")
    print("=" * 48 + "\n")

    # ── Phase 4: Run pipeline ──
    try:
        if args.no_vad and not args.loop:
            # Single turn
            return _run_single_turn(args)
        elif args.loop:
            return _run_manual_loop(args)
        else:
            return _run_vad_loop(args)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        for _, proc in processes:
            if proc:
                proc.terminate()
        print("All services stopped.")

    return 0


def _run_single_turn(args: argparse.Namespace) -> int:
    from main import build_pipeline_request, parse_args as _m_parse, run_pipeline, print_turn
    pipeline_args = _build_pipeline_args(args)
    print_turn(run_pipeline(build_pipeline_request(pipeline_args)))
    return 0


def _run_manual_loop(args: argparse.Namespace) -> int:
    from main import build_pipeline_request, print_turn, run_pipeline
    pipeline_args = _build_pipeline_args(args)
    turn = 0
    print("Press Enter for next turn, or type q to quit.")
    while True:
        cmd = input("Next turn> ").strip().lower()
        if cmd in {"q", "quit", "exit"}:
            return 0
        turn += 1
        try:
            print_turn(run_pipeline(build_pipeline_request(pipeline_args)))
        except Exception as exc:
            print(f"Error: {exc}")
        if args.turns and turn >= args.turns:
            return 0


def _run_vad_loop(args: argparse.Namespace) -> int:
    from main import build_pipeline_request, print_turn, run_pipeline
    pipeline_args = _build_pipeline_args(args)
    turn = 0
    silent_turns = 0

    while True:
        turn += 1
        print(f"[{turn}] Listening...")
        try:
            print_turn(run_pipeline(build_pipeline_request(pipeline_args)))
            silent_turns = 0
        except RuntimeError as exc:
            if "no speech" in str(exc).lower():
                silent_turns += 1
                if silent_turns >= 10:
                    print("Auto-exiting after 10 silent rounds.")
                    return 0
            else:
                print(f"[{turn}] Error: {exc}")
        except Exception as exc:
            print(f"[{turn}] Error: {exc}")

        if args.turns and turn >= args.turns:
            return 0
        time.sleep(0.3)


def _build_pipeline_args(args: argparse.Namespace):
    class PipelineArgs:
        seconds = args.seconds
        sample_rate = args.sample_rate
        language = None
        memory_limit = args.memory_limit
        audio_path = None
        no_tts = args.no_tts
        tts_engine = args.tts_engine
        tts_voice = args.tts_voice
        tts_emotion = args.tts_emotion
        tts_speed = args.tts_speed
        vad = True
        vad_silence_timeout = args.vad_silence_timeout
        vad_max_duration = args.vad_max_duration
        turns = args.turns
        loop = False
        auto_loop = False
        env_file = args.env_file
    return PipelineArgs()


if __name__ == "__main__":
    raise SystemExit(main())

