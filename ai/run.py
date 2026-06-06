"""v1 Voice Agent  --one-click launcher with input state machine.

Usage:
    python run.py              # Continuous VAD mode
    python run.py --no-vad     # Single-turn (fixed duration)
    python run.py --ui         # TUI control panel
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
import io
import requests

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# --- Force UTF-8 for all I/O (fix garbled text on Windows) ---
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from app.core.config import DEFAULT_ENV_PATH, load_env_file


SERVICES = [
    ("asr",    "app.modules.asr.api",    os.environ.get("ASR_PORT", "8000")),
    ("llm",    "app.modules.llm.api",    os.environ.get("LLM_PORT", "8020")),
    ("tts",    "app.modules.tts.api",    os.environ.get("TTS_PORT", "8030")),
    ("memory", "app.modules.memory.api", os.environ.get("MEMORY_PORT", "8040")),
]


# ---- GSVI v2Pro (nvidia50) via api_v2.py ----
GSVI_DIR = BASE_DIR / "models" / "tts" / "GPT-SoVITS-v2pro-20250604-nvidia50"
GSVI_PYTHON = GSVI_DIR / "runtime" / "python.exe"
GSVI_CONFIG = GSVI_DIR / "GPT_SoVITS" / "configs" / "tts_infer.yaml"

SERVICE_TIMEOUTS = {"asr": 60.0, "gsvi-v2pro": 180.0, "tts": 120.0}


def env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return v.strip().lower() in {"1", "true", "yes", "on"} if v else default


def start_services(args: argparse.Namespace, log_dir: Path) -> tuple[list[subprocess.Popen], list]:
    procs: list[subprocess.Popen] = []
    log_files = []
    child_env = os.environ.copy()
    child_env.setdefault("PYTHONIOENCODING", "utf-8")
    child_env.setdefault("PYTHONUTF8", "1")

    if env_bool("START_GSVI", True):
        os.environ.setdefault("GSVI_PORT", "8050")
        os.environ.setdefault("GSVI_URL", "http://127.0.0.1:8050")
        env = child_env.copy()
        env["PATH"] = f"{GSVI_DIR / 'runtime'};{env.get('PATH', '')}"
        env["BROWSER"] = "none"
        cmd = [str(GSVI_PYTHON), str(GSVI_DIR / "api_v2.py"),
               "-a", "127.0.0.1", "-p", "8050", "-c", str(GSVI_CONFIG)]
        print(f"[start] GSVI-v2pro cmd: {' '.join(cmd)}")
        print(f"[start] GSVI-v2pro cwd: {GSVI_DIR}")
        gsvi_log = open(str(log_dir / "gsvi.log"), "w", encoding="utf-8")
        log_files.append(gsvi_log)
        p = subprocess.Popen(cmd, cwd=GSVI_DIR, env=env, stdout=gsvi_log, stderr=gsvi_log)
        procs.append(p)
        print("[start] GSVI-v2pro ->:8050")

    for name, module, port in SERVICES:
        cmd = [sys.executable, "-m", module]
        if module in {"app.modules.llm.api", "app.modules.tts.api"}:
            cmd.extend(["--env-file", str(args.env_file)])
        cmd.extend(["--host", "127.0.0.1", "--port", port])
        svc_log = open(str(log_dir / f"{name}.log"), "w", encoding="utf-8")
        log_files.append(svc_log)
        print(f"[start] {name} cmd: {sys.executable} -m {module} --port {port}")
        p = subprocess.Popen(cmd, cwd=BASE_DIR, stdout=svc_log, stderr=svc_log, env=child_env)
        procs.append(p)
        print(f"[start] {name} ->:{port}  pid={p.pid}")
    return procs, log_files


def wait_services() -> bool:
    all_services = [(s[0], s[2]) for s in SERVICES]
    if env_bool("START_GSVI", True):
        all_services.insert(0, ("gsvi-v2pro", "8050"))
    ok = True
    for name, port in all_services:
        timeout = SERVICE_TIMEOUTS.get(name, 15.0)
        url = f"http://127.0.0.1:{port}/health"
        start = time.time()
        ready = False
        while time.time() - start < timeout:
            try:
                r = requests.get(url, timeout=2)
                # Some services (gsvi-v2pro) does not expose /health;
                # any HTTP response (including 404) means the server is alive.
                if r.status_code in (200, 404):
                    ready = True
                    break
            except Exception:
                pass
            time.sleep(0.5)
        if ready:
            print(f"[ready] {name} ({time.time() - start:.1f}s)")
            try:
                from app.core.event_bus import bus
                svc_name = "tts" if name.startswith("gsvi") else name
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
    p.add_argument("--no-tts", action="store_true")
    p.add_argument("--no-vad", action="store_true", help="Single-turn mode")
    p.add_argument("--tts-engine", choices=["gsvi", "gsvi-v2pro", "pyttsx3"])
    p.add_argument("--ui", action="store_true", help="Launch TUI control panel")
    p.add_argument("--persona", default=None)
    p.add_argument("--text", action="store_true", help="Text-only chat mode (no audio)")
    p.add_argument("--audio-path", default="")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    dotenv_path = Path(args.env_file)
    if dotenv_path.exists():
        load_env_file(dotenv_path)

    # Persona
    if args.persona:
        try:
            persona_id = args.persona
            char_path = BASE_DIR / "characters" / persona_id / "character.json"
            with open(char_path, "r", encoding="utf-8") as f:
                char_card = json.load(f)
            persona_text = char_card.get("character_setting") or char_card.get("system_prompt", "")
            if persona_text:
                os.environ["LLM_STREAM_SYSTEM_PROMPT"] = persona_text
                os.environ["LLM_SYSTEM_PROMPT"] = persona_text

            tts_cfg = char_card.get("tts", {})
            if tts_cfg.get("voice"):
                os.environ["GSVI_VOICE"] = tts_cfg["voice"]
            if tts_cfg.get("ref_audio"):
                ref_audio = tts_cfg["ref_audio"]
                if isinstance(ref_audio, dict):
                    first_key = next(iter(ref_audio))
                    ref_audio = ref_audio[first_key]
                os.environ["GSVI_REF_AUDIO"] = str(BASE_DIR / "characters" / persona_id / ref_audio)
            if tts_cfg.get("prompt_lang"):
                lang_map = {"ja": "日语", "zh": "中文", "en": "英文", "ko": "韩文"}
                raw_lang = tts_cfg["prompt_lang"]
                os.environ["GSVI_PROMPT_LANG"] = lang_map.get(raw_lang, raw_lang)
            if tts_cfg.get("prompt_text"):
                os.environ["GSVI_PROMPT_TEXT"] = tts_cfg["prompt_text"]
            os.environ.setdefault("GSVI_EMOTION", "默认")
            # ---- Pass custom model weight paths (relative to GSVI dir) ----
            custom_model = tts_cfg.get("custom_model", {})
            if custom_model.get("t2s"):
                t2s_name = Path(custom_model["t2s"]).name
                os.environ["GSVI_GPT_WEIGHTS"] = f"GPT_weights_v2Pro/{persona_id}/{t2s_name}"
            if custom_model.get("vits"):
                vits_name = Path(custom_model["vits"]).name
                os.environ["GSVI_SOVITS_WEIGHTS"] = f"SoVITS_weights_v2Pro/{persona_id}/{vits_name}"

            print(f"[persona] Loaded: {persona_id} ({len(persona_text)} chars)")
            print(f"[persona]   engine={tts_cfg.get('engine','')}  voice={tts_cfg.get('voice','')}")
            print(f"[persona]   prompt_lang={tts_cfg.get('prompt_lang','')}  prompt_text={tts_cfg.get('prompt_text','')[:60]}...")
            ref = tts_cfg.get('ref_audio', {})
            print(f"[persona]   ref_audio={ref}")
        except Exception as exc:
            print(f"[persona] Load failed: {exc}")

    # Setup logging
    from datetime import datetime
    log_dir = BASE_DIR / "logs" / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n[log] {log_dir}")

    print("\nStarting services...")
    procs, log_files = start_services(args, log_dir)
    try:
        print("\nWaiting for services...")
        if not wait_services():
            return 1

        print("\nWarming up TTS...")
        try:
            tts_port = os.environ.get("TTS_PORT", "8030")
            r = requests.post(f"http://127.0.0.1:{tts_port}/v1/tts/synthesize",
                             json={"text": "你好", "language": "zh"},
                             timeout=180)
            if r.status_code == 200:
                print("[warmup] TTS model loaded")
            else:
                print(f"[warmup] TTS returned {r.status_code}")
        except Exception as e:
            print(f"[warmup] TTS warmup skipped: {e}")

        # Warmup ASR
        print("\nWarming up ASR...")
        import tempfile
        import numpy as np
        import soundfile as sf
        warmup_audio = np.zeros(16000, dtype=np.float32)
        warmup_path = Path(tempfile.gettempdir()) / "_asr_warmup.wav"
        sf.write(str(warmup_path), warmup_audio, 16000)
        try:
            asr_port = os.environ.get("ASR_PORT", "8000")
            r = requests.post(f"http://127.0.0.1:{asr_port}/v1/asr/transcribe",
                             json={"audio_path": str(warmup_path), "language": None},
                             timeout=120)
            r.raise_for_status()
            print("[warmup] ASR model loaded")
        except Exception:
            print("[warmup] ASR warmup skipped (will load on first utterance)")
        finally:
            warmup_path.unlink(missing_ok=True)

        # ---- Single-turn mode (Brain-based, no Orchestrator) ----
        if args.no_vad:
            import sounddevice as sd
            from app.models import OpenAILLMAdapter
            from app.character.registry import CharacterRegistry
            from app.tools.registry import ToolRegistry
            from app.runtime.agent_runtime import AgentRuntime
            from app.runtime.turn import TurnRuntime
            from app.tts.player import AsyncAudioPlayer

            path = Path(args.audio_path) if args.audio_path else BASE_DIR / "recordings" / "single.wav"

            if not args.audio_path:
                print(f"Recording {args.seconds}s...")
                audio = sd.rec(int(args.seconds * args.sample_rate),
                               samplerate=args.sample_rate, channels=1, dtype="float32")
                sd.wait()
                path.parent.mkdir(parents=True, exist_ok=True)
                sf.write(str(path), audio, args.sample_rate)

            # Brain-based single turn
            char = CharacterRegistry()
            if args.persona:
                char.activate(args.persona)
            tools = ToolRegistry()
            runtime = AgentRuntime(character=char, tools=tools)
            adapter = OpenAILLMAdapter()
            player = AsyncAudioPlayer()
            player.start()

            turns = TurnRuntime(runtime, llm_adapter=adapter, player=player)
            turns.start()

            try:
                result = turns.process_audio(str(path), args.language)
                if result.ok:
                    print(f"User: {result.user_text}")
                    print(f"Assistant: {result.reply_text}")
                else:
                    print(f"Error: {result.error}")
                turns.wait_output_done(timeout=30.0)
            finally:
                turns.shutdown()

        else:
            if args.ui:
                from app.ui import VoiceAgentUI
                VoiceAgentUI(persona=args.persona, text_mode=args.text).run()
            else:
                from app.agent.loop import AgentLoop
                loop = AgentLoop(persona=args.persona, text_mode=args.text)
                loop.start()

        return 0
    finally:
        print("Shutting down...")
        for p in procs:
            try:
                p.terminate()
                print(f"[stop] pid={p.pid} terminated")
            except Exception as exc:
                print(f"[stop] pid={p.pid} error: {exc}")
        for f in log_files:
            try: f.close()
            except Exception: pass
        print("All services stopped.")


if __name__ == "__main__":
    raise SystemExit(main())
