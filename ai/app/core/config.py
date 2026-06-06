import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
MODELS_DIR = BASE_DIR / "models"
DEFAULT_AUDIO_PATH = BASE_DIR / "recordings" / "last_recording.wav"
DEFAULT_MEMORY_PATH = BASE_DIR / "memory" / "memory.jsonl"
DEFAULT_MODEL_DIR = MODELS_DIR / "asr" / "Qwen3-ASR-1.7B"
DEFAULT_ENV_PATH = BASE_DIR / ".env"

RECORDER_URL = os.environ.get("RECORDER_URL", "http://127.0.0.1:8010")
ASR_URL = os.environ.get("ASR_URL", "http://127.0.0.1:8000")
LLM_URL = os.environ.get("LLM_URL", "http://127.0.0.1:8020")
TTS_URL = os.environ.get("TTS_URL", "http://127.0.0.1:8030")
MEMORY_URL = os.environ.get("MEMORY_URL", "http://127.0.0.1:8040")

# ---- GSVI v2Pro (nvidia50) ----
GSVI_DIR = MODELS_DIR / "tts" / "GPT-SoVITS-v2pro-20250604-nvidia50"
GSVI_PYTHON = GSVI_DIR / "runtime" / "python.exe"
GSVI_SCRIPT = GSVI_DIR / "api_v2.py"
GSVI_HEADLESS = BASE_DIR / "scripts" / "run_gsvi_headless.py"
GSVI_CONFIG_PATH = GSVI_DIR / "GPT_SoVITS" / "configs" / "tts_infer.yaml"
GSVI_URL = os.environ.get("GSVI_URL", "http://127.0.0.1:8050")


# ---- uvicorn log config (adds timestamps) ----
UVICORN_LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": "%(asctime)s %(levelprefix)s %(message)s",
            "datefmt": "%H:%M:%S",
            "use_colors": True,
        },
        "access": {
            "()": "uvicorn.logging.AccessFormatter",
            "fmt": "%(asctime)s %(levelprefix)s %(client_addr)s - \"%(request_line)s\" %(status_code)s",
            "datefmt": "%H:%M:%S",
            "use_colors": True,
        },
    },
    "handlers": {
        "default": {"formatter": "default", "class": "logging.StreamHandler", "stream": "ext://sys.stderr"},
        "access": {"formatter": "access", "class": "logging.StreamHandler", "stream": "ext://sys.stdout"},
    },
    "loggers": {
        "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"level": "INFO"},
        "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
    },
}

DEFAULT_TTS_ENGINE = os.environ.get("TTS_ENGINE", "gsvi-v2pro").lower()
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
            value = value.split("#")[0]  # strip inline comment
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
