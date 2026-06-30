"""Start backend services + Live2D bridge."""
import os, sys, time, subprocess, signal, threading
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
from app.core.config import DEFAULT_ENV_PATH, load_env_file
load_env_file(DEFAULT_ENV_PATH)
import argparse
from run import start_services, wait_services
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser on start")
    parsed, _ = parser.parse_known_args()
    args = argparse.Namespace(env_file=str(BASE_DIR / "config" / ".env"))
    import tempfile
    log_dir = Path(tempfile.gettempdir()) / "monika-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    print("Starting backend services...")
    procs, log_files = start_services(args, log_dir)
    try:
        if not wait_services():
            print("[FAIL] Some services not ready"); return 1
        import requests, numpy as np, soundfile as sf
        # Warmup TTS
        print("\\nWarming up TTS...")
        tts_port = os.environ.get("TTS_PORT", "8030")
        try:
            r = requests.post(f"http://127.0.0.1:{tts_port}/v1/tts/synthesize",
                json={"text": "test", "language": "zh"}, timeout=180)
            if r.status_code == 200: print("[warmup] TTS ready")
        except Exception as e: print(f"[warmup] TTS skipped: {e}")
        # Warmup ASR
        print("Warming up ASR...")
        wp = Path(tempfile.gettempdir()) / "_asr_warmup.wav"
        sf.write(str(wp), np.zeros(16000, dtype=np.float32), 16000)
        try:
            asr_port = os.environ.get("ASR_PORT", "8000")
            requests.post(f"http://127.0.0.1:{asr_port}/v1/asr/transcribe",
                json={"audio_path": str(wp)}, timeout=120)
            print("[warmup] ASR ready")
        except Exception: print("[warmup] ASR skipped")
        finally: wp.unlink(missing_ok=True)
        # Start bridge
        bridge_port = os.environ.get("BRIDGE_PORT", "9528")
        print(f"\\nStarting Live2D Bridge on http://127.0.0.1:{bridge_port} ...")
        bridge_proc = subprocess.Popen([sys.executable, "-m", "app.bridge.server"], cwd=BASE_DIR)
        if not parsed.no_browser:
            import webbrowser
            webbrowser.open(f"http://127.0.0.1:{bridge_port}")
        print(f"\\n=== Monika Live2D ready! http://127.0.0.1:{bridge_port} ===")
        print("    Press Ctrl+C to stop\\n")
        shutdown_event = threading.Event()
        def _handle_signal(*_): shutdown_event.set()
        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
        shutdown_event.wait()
    finally:
        print("\\nShutting down...")
        try: bridge_proc.terminate()
        except: pass
        for p in procs:
            try: p.terminate()
            except: pass
        for f in log_files:
            try: f.close()
            except: pass
        print("Done.")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
