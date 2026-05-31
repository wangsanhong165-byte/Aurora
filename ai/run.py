"""
v1 Voice Agent — one-click launcher with input state machine.

Usage:
    python run.py              # Continuous VAD mode
    python run.py --no-vad     # Single-turn (fixed duration)
    python run.py --ui         # TUI control panel
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

from app.core.config import DEFAULT_ENV_PATH, load_env_file

SERVICES = [
    ("asr",    "app.modules.asr.api",    "8000"),
    ("llm",    "app.modules.llm.api",    "8020"),
    ("tts",    "app.modules.tts.api",    "8030"),
    ("memory", "app.modules.memory.api", "8040"),
]

GSVI_DIR = BASE_DIR / "models" / "tts" / "GPT-SoVITS-1007-cu128"
GSVI_HEADLESS = BASE_DIR / "scripts" / "run_gsvi_headless.py"
GSVI_PYTHON = GSVI_DIR / "runtime" / "python.exe"
GSVI_CONFIG = GSVI_DIR / "GPT_SoVITS" / "configs" / "tts_infer.yaml"

SERVICE_TIMEOUTS = {"asr": 60.0, "gsvi": 120.0, "tts": 120.0}


def env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return v.strip().lower() in {"1", "true", "yes", "on"} if v else default


def start_services(args: argparse.Namespace) -> list[subprocess.Popen]:
    procs: list[subprocess.Popen] = []

    if env_bool("START_GSVI", True):
        os.environ.setdefault("GSVI_PORT", "8050")
        os.environ.setdefault("GSVI_URL", "http://127.0.0.1:8050")
        cmd = [str(GSVI_PYTHON), str(GSVI_HEADLESS), "-s", "127.0.0.1", "-p", "8050", "-c", str(GSVI_CONFIG)]
        env = os.environ.copy()
        env["PATH"] = f"{GSVI_DIR / 'runtime'};{env.get('PATH', '')}"
        p = subprocess.Popen(cmd, cwd=GSVI_DIR, env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(p)
        print("[start] GSVI → :8050")

    for name, module, port in SERVICES:
        cmd = [sys.executable, "-m", module]
        if module in {"app.modules.llm.api", "app.modules.tts.api"}:
            cmd.extend(["--env-file", str(args.env_file)])
        cmd.extend(["--host", "127.0.0.1", "--port", port])
        p = subprocess.Popen(cmd, cwd=BASE_DIR,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(p)
        print(f"[start] {name} → :{port}")
    return procs


def wait_services() -> bool:
    all_services = [(s[0], s[2]) for s in SERVICES]
    if env_bool("START_GSVI", False):
        all_services.insert(0, ("gsvi", "8050"))
    ok = True
    for name, port in all_services:
        timeout = SERVICE_TIMEOUTS.get(name, 15.0)
        url = f"http://127.0.0.1:{port}/health"
        start = time.time()
        ready = False
        while time.time() - start < timeout:
            try:
                r = requests.get(url, timeout=2)
                if r.status_code == 200:
                    ready = True
                    break
            except Exception:
                pass
            time.sleep(0.5)
        if ready:
            print(f"[ready] {name} ({time.time() - start:.1f}s)")
            try:
                from app.core.event_bus import bus
                svc_name = "tts" if name == "gsvi" else name
                bus.emit("service_status", {"name": svc_name, "status": "READY"})
            except Exception:
                pass
        else:
            print(f"[FAIL]  {name} not ready")
            ok = False
    return ok


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="v1 Voice Agent")
    p.add_argument("--env-file", default=str(DEFAULT_ENV_PATH))
    p.add_argument("--seconds", type=float, default=5.0)
    p.add_argument("--sample-rate", type=int, default=16000)
    p.add_argument("--language", default=None)
    p.add_argument("--memory-limit", type=int, default=8)
    p.add_argument("--audio-path")
    p.add_argument("--no-tts", action="store_true")
    p.add_argument("--no-vad", action="store_true", help="Single-turn mode")
    p.add_argument("--tts-engine", choices=["gsvi", "pyttsx3"])
    p.add_argument("--ui", action="store_true", help="Launch TUI control panel")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    load_env_file(Path(args.env_file))
    os.environ.setdefault("TTS_ENGINE", "gsvi")

    print("\nStarting services...")
    procs = start_services(args)
    try:
        print("\nWaiting for services...")
        if not wait_services():
            return 1

        # Warmup ASR model (first call loads from disk ~9s, avoid on first utterance)
        print("\nWarming up ASR...")
        import tempfile
        import numpy as np
        import soundfile as sf
        warmup_audio = np.zeros(16000, dtype=np.float32)
        warmup_path = Path(tempfile.gettempdir()) / "_asr_warmup.wav"
        sf.write(str(warmup_path), warmup_audio, 16000)
        try:
            r = requests.post("http://127.0.0.1:8000/v1/asr/transcribe",
                             json={"audio_path": str(warmup_path), "language": None},
                             timeout=120)
            r.raise_for_status()
            print("[warmup] ASR model loaded")
        except Exception:
            print("[warmup] ASR warmup skipped (will load on first utterance)")
        finally:
            warmup_path.unlink(missing_ok=True)

        # Warmup TTS model (first load ~60s, avoid on first utterance)
        print("\nWarming up TTS...")
        try:
            r = requests.post("http://127.0.0.1:8030/v1/tts/synthesize",
                             json={"text": "测试", "speaker": "serena", "language": "zh"},
                             timeout=180)
            if r.status_code == 200:
                print("[warmup] TTS model loaded")
            else:
                print(f"[warmup] TTS returned {r.status_code}")
        except Exception as e:
            print(f"[warmup] TTS warmup skipped: {e}")

        if args.no_vad:
            import sounddevice as sd
            import soundfile as sf
            from app.agent.orchestrator import Orchestrator

            orch = Orchestrator()
            path = Path(args.audio_path) if args.audio_path else BASE_DIR / "recordings" / "single.wav"

            if not args.audio_path:
                print(f"Recording {args.seconds}s...")
                audio = sd.rec(int(args.seconds * args.sample_rate),
                               samplerate=args.sample_rate, channels=1, dtype="float32")
                sd.wait()
                path.parent.mkdir(parents=True, exist_ok=True)
                sf.write(str(path), audio, args.sample_rate)

            result = orch.run_turn(str(path), args.language)
            print(f"User: {result['user_text']}")
            print(f"Assistant: {result['reply_text']}")
        else:
            from app.agent.loop import AgentLoop
            agent = AgentLoop()
            if args.ui:
                import threading
                from app.ui import VoiceAgentUI
                agent_thread = threading.Thread(target=agent.run, daemon=True)
                agent_thread.start()
                VoiceAgentUI().run()
                agent.stop()
            else:
                agent.run()

        return 0
    finally:
        print("Shutting down...")
        for p in procs:
            p.terminate()
        print("All services stopped.")


if __name__ == "__main__":
    raise SystemExit(main())

