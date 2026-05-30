import argparse
import os
import subprocess
import sys
from pathlib import Path

from app.core.config import DEFAULT_ENV_PATH, GSVI_CONFIG_PATH, GSVI_DIR, GSVI_HEADLESS, GSVI_PYTHON, load_env_file


BASE_DIR = Path(__file__).resolve().parent

SERVICES = [
    ("recorder", "app.modules.recorder.api", "8010"),
    ("asr", "app.modules.asr.api", "8000"),
    ("llm", "app.modules.llm.api", "8020"),
    ("tts", "app.modules.tts.api", "8030"),
    ("memory", "app.modules.memory.api", "8040"),
]


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def start_gsvi(host: str, port: str) -> subprocess.Popen:
    if not GSVI_PYTHON.exists():
        raise RuntimeError(f"GPT-SoVITS runtime not found: {GSVI_PYTHON}")
    if not GSVI_HEADLESS.exists():
        raise RuntimeError(f"GSVI headless wrapper not found: {GSVI_HEADLESS}")

    command = [
        str(GSVI_PYTHON),
        str(GSVI_HEADLESS),
        "-s",
        host,
        "-p",
        port,
        "-c",
        str(GSVI_CONFIG_PATH),
    ]
    env = os.environ.copy()
    env["PATH"] = f"{GSVI_DIR / 'runtime'};{env.get('PATH', '')}"
    return subprocess.Popen(command, cwd=GSVI_DIR, env=env)


def main() -> int:
    parser = argparse.ArgumentParser(description="Start all local voice assistant API services")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--with-gsvi", action="store_true", help="Start GPT-SoVITS GSVI service too")
    parser.add_argument("--gsvi-port", default="8050")
    args = parser.parse_args()
    load_env_file(Path(args.env_file))

    processes: list[subprocess.Popen] = []
    try:
        should_start_gsvi = args.with_gsvi or (
            os.environ.get("TTS_ENGINE", "gsvi").lower() == "gsvi" and env_bool("START_GSVI", True)
        )
        if should_start_gsvi:
            gsvi_port = os.environ.get("GSVI_PORT", args.gsvi_port)
            os.environ.setdefault("GSVI_PORT", gsvi_port)
            os.environ.setdefault("GSVI_URL", f"http://{args.host}:{gsvi_port}")
            process = start_gsvi(args.host, gsvi_port)
            processes.append(process)
            print(f"gsvi API started: http://{args.host}:{gsvi_port}")

        for name, module, port in SERVICES:
            command = [
                sys.executable,
                "-m",
                module,
            ]
            if module in {"app.modules.llm.api", "app.modules.tts.api"}:
                command.extend(["--env-file", str(args.env_file)])
            command.extend(["--host", args.host, "--port", port])
            process = subprocess.Popen(command, cwd=BASE_DIR)
            processes.append(process)
            print(f"{name} API started: http://{args.host}:{port}")

        print("All services started. Press Ctrl+C to stop.")
        for process in processes:
            process.wait()
        return 0
    except KeyboardInterrupt:
        print("Stopping services...")
        for process in processes:
            process.terminate()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
