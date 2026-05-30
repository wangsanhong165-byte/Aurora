"""
v1 Voice Agent — one-click launcher with input state machine.

Usage:
    python run.py              # Continuous VAD mode
    python run.py --no-vad     # Single-turn (fixed duration)
    python run.py --loop       # Manual Enter-between-turns
"""
import argparse
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

# ── Ensure project root on path ──
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from app.core.config import DEFAULT_ENV_PATH, load_env_file

# ── Services we still run as HTTP ──
SERVICES = [
    ("asr",    "app.modules.asr.api",    "8000"),
    ("llm",    "app.modules.llm.api",    "8020"),
    ("tts",    "app.modules.tts.api",    "8030"),
    ("memory", "app.modules.memory.api", "8040"),
]

GSVI_DIR = BASE_DIR / "models" / "GPT-SoVITS-1007-cu128"
GSVI_HEADLESS = BASE_DIR / "scripts" / "run_gsvi_headless.py"
GSVI_PYTHON = GSVI_DIR / "runtime" / "python.exe"
GSVI_CONFIG = GSVI_DIR / "GPT_SoVITS" / "configs" / "tts_infer.yaml"

SERVICE_TIMEOUTS = {"asr": 60.0, "gsvi": 120.0}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return v.strip().lower() in {"1", "true", "yes", "on"} if v else default


# ── Service lifecycle ───────────────────────────────────────────

def start_services(args: argparse.Namespace) -> list[subprocess.Popen]:
    procs: list[subprocess.Popen] = []

    # GSVI
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
    all_services = [("gsvi", "8050")] + [(s[0], s[2]) for s in SERVICES]
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
        else:
            print(f"[FAIL]  {name} not ready")
            ok = False
    return ok


# ── Pipeline ────────────────────────────────────────────────────

def transcribe(path: str, language: str | None = None) -> tuple[str, str | None]:
    r = requests.post("http://127.0.0.1:8000/v1/asr/transcribe",
                      json={"audio_path": path, "language": language}, timeout=120)
    r.raise_for_status()
    body = r.json()
    return body["result"]["text"].strip(), body["result"].get("language")


def chat(text: str, context: list[dict]) -> dict:
    r = requests.post("http://127.0.0.1:8020/v1/llm/chat",
                      json={"event": {"event_id": str(uuid.uuid4()),
                                      "created_at": utc_now(),
                                      "transcript": text,
                                      "language": None,
                                      "metadata": {}},
                            "recent_memory": context},
                      timeout=120)
    r.raise_for_status()
    return r.json()


def speak(text: str, engine: str | None = None) -> None:
    payload = {"text": text}
    if engine:
        payload["engine"] = engine
    requests.post("http://127.0.0.1:8030/v1/tts/speak", json=payload, timeout=180)


def load_context(limit: int = 8) -> list[dict]:
    try:
        r = requests.post("http://127.0.0.1:8040/v1/memory/recent",
                          json={"limit": limit}, timeout=10)
        return r.json().get("items", [])
    except Exception:
        return []


def save_memory(text: str, reply: dict) -> None:
    try:
        requests.post("http://127.0.0.1:8040/v1/memory/append",
                      json={"event": {"event_id": str(uuid.uuid4()),
                                      "created_at": utc_now(),
                                      "transcript": text,
                                      "metadata": {}},
                            "reply": reply},
                      timeout=10)
    except Exception:
        pass


# ── Run modes ───────────────────────────────────────────────────

def run_vad_loop() -> int:
    from app.core.state import InputState
    from app.input import InputManager

    mgr = InputManager(silence_timeout=1.5, max_duration=30.0)
    mgr.start()

    print("\n" + "=" * 48)
    print("  All services ready — listening now")
    print("  Speak to interact. Ctrl+C to stop.")
    print("=" * 48 + "\n")

    turn = 0
    silent_turns = 0
    error_turns = 0

    try:
        while True:
            turn += 1
            print(f"[{turn}] Listening...")

            event = mgr.poll()
            if event["type"] == "stop":
                break

            if event["type"] != "speech":
                silent_turns += 1
                if silent_turns >= 10:
                    print("Auto-exiting after 10 silent rounds.")
                    break
                continue

            silent_turns = 0
            audio_path = event["audio_path"]

            try:
                text, lang = transcribe(audio_path)
                if not text:
                    raise RuntimeError("ASR returned empty text.")

                print(f"    User: {text}")

                ctx = load_context()
                reply = chat(text, ctx)
                reply_text = reply.get("reply_text", "").strip()

                print(f"    Assistant: {reply_text}")

                speak(reply_text)
                save_memory(text, reply)

                error_turns = 0

            except Exception as exc:
                error_turns += 1
                print(f"[{turn}] Error: {exc}")
                if error_turns >= 5:
                    print("Auto-exiting after 5 consecutive errors.")
                    break

            mgr.transition(InputState.IDLE)

        return 0
    except KeyboardInterrupt:
        print(f"\nStopped after {turn} turn(s).")
        return 0
    finally:
        mgr.stop()


def run_single_turn(args: argparse.Namespace) -> int:
    import sounddevice as sd
    import soundfile as sf
    path = Path(args.audio_path) if args.audio_path else BASE_DIR / "recordings" / "single.wav"

    if not args.audio_path:
        print(f"Recording {args.seconds}s...")
        audio = sd.rec(int(args.seconds * args.sample_rate),
                       samplerate=args.sample_rate, channels=1, dtype="float32")
        sd.wait()
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(path), audio, args.sample_rate)

    text, _ = transcribe(str(path), args.language)
    print(f"User: {text}")

    ctx = load_context(args.memory_limit)
    reply = chat(text, ctx)
    reply_text = reply.get("reply_text", "").strip()
    print(f"Assistant: {reply_text}")

    if not args.no_tts:
        speak(reply_text, args.tts_engine)
    save_memory(text, reply)
    return 0


# ── CLI ─────────────────────────────────────────────────────────

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
    p.add_argument("--loop", action="store_true", help="Manual mode (Enter between turns)")
    p.add_argument("--tts-engine", choices=["gsvi", "pyttsx3"])
    p.add_argument("--tts-voice")
    p.add_argument("--tts-emotion")
    p.add_argument("--tts-speed", type=float)
    p.add_argument("--vad-silence-timeout", type=float, default=1.5)
    p.add_argument("--vad-max-duration", type=float, default=30.0)
    p.add_argument("--turns", type=int, default=0)
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

        if args.no_vad or args.loop:
            return run_single_turn(args) if args.no_vad else 0
        return run_vad_loop()

    finally:
        print("Shutting down...")
        for p in procs:
            p.terminate()
        print("All services stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


