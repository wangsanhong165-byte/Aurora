import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
MODELS_DIR = BASE_DIR / "models"
DEFAULT_AUDIO_PATH = BASE_DIR / "last_recording.wav"
DEFAULT_MEMORY_PATH = BASE_DIR / "memory.short.jsonl"
DEFAULT_MODEL_DIR = MODELS_DIR / "Qwen3-ASR-1.7B"
DEFAULT_ENV_PATH = BASE_DIR / ".env"

RECORDER_URL = os.environ.get("RECORDER_URL", "http://127.0.0.1:8010")
ASR_URL = os.environ.get("ASR_URL", "http://127.0.0.1:8000")
LLM_URL = os.environ.get("LLM_URL", "http://127.0.0.1:8020")
TTS_URL = os.environ.get("TTS_URL", "http://127.0.0.1:8030")
MEMORY_URL = os.environ.get("MEMORY_URL", "http://127.0.0.1:8040")

GSVI_DIR = MODELS_DIR / "GPT-SoVITS-1007-cu128"
GSVI_PYTHON = GSVI_DIR / "runtime" / "python.exe"
GSVI_SCRIPT = GSVI_DIR / "gsvi.py"
GSVI_HEADLESS = BASE_DIR / "scripts" / "run_gsvi_headless.py"
GSVI_CONFIG_PATH = GSVI_DIR / "GPT_SoVITS" / "configs" / "tts_infer.yaml"
GSVI_URL = os.environ.get("GSVI_URL", "http://127.0.0.1:8050")

DEFAULT_TTS_ENGINE = os.environ.get("TTS_ENGINE", "gsvi").lower()
DEFAULT_TTS_OUTPUT_DIR = BASE_DIR / "tts_outputs"


def load_env_file(path: Path = DEFAULT_ENV_PATH) -> None:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
