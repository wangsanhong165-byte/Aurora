# Modular Voice Assistant

The project is organized as one pipeline entry plus independent API modules.

## Structure

```text
.
├── main.py
├── start_services.py
├── requirements.txt
├── .env.example
├── app/
│   ├── core/
│   │   ├── config.py
│   │   └── schemas.py
│   └── modules/
│       ├── recorder/api.py
│       ├── asr/api.py
│       ├── llm/api.py
│       ├── tts/api.py
│       └── memory/api.py
└── Qwen3-ASR-1.7B/
```

## Main Files

| Path | Purpose |
| --- | --- |
| `main.py` | Main pipeline entry. It only orchestrates module APIs. |
| `start_services.py` | Starts all local API services. |
| `app/core/config.py` | Default paths, service URLs, `.env` loading. |
| `app/core/schemas.py` | Shared request/response schemas. |
| `app/modules/recorder/api.py` | Microphone recording API, port `8010`. |
| `app/modules/asr/api.py` | Local Qwen3-ASR API, port `8000`. |
| `app/modules/llm/api.py` | Cloud LLM adapter API, port `8020`. |
| `app/modules/tts/api.py` | Local TTS API, port `8030`. |
| `app/modules/memory/api.py` | Short-term memory API, port `8040`. |

## Install

Python 3.12 is recommended:

```powershell
conda create -n qwen-asr python=3.12 -y
conda activate qwen-asr
python -m pip install --upgrade pip
```

For RTX 5060, install CUDA 12.8 PyTorch:

```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```

Install project dependencies:

```powershell
pip install -r requirements.txt
```

## DeepSeek LLM Config

Copy `.env.example` to `.env`:

```powershell
Copy-Item .env.example .env
```

Default DeepSeek config:

```text
LLM_API_KEY_ENV=DEEPSEEK_API_KEY
DEEPSEEK_API_KEY=your_deepseek_api_key_here
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-pro
LLM_REASONING_EFFORT=high
LLM_THINKING_TYPE=enabled
LLM_RESPONSE_FORMAT=json_object
```

To switch to another OpenAI-compatible model, only change `.env`:

```text
LLM_API_KEY_ENV=OPENAI_API_KEY
OPENAI_API_KEY=your_openai_api_key_here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4.1-mini
LLM_REASONING_EFFORT=
LLM_THINKING_TYPE=none
```

The LLM adapter uses the official `openai` Python SDK and supports:

```text
LLM_BASE_URL
LLM_MODEL
LLM_API_KEY_ENV
LLM_REASONING_EFFORT
LLM_THINKING_TYPE
LLM_RESPONSE_FORMAT
LLM_TEMPERATURE
LLM_TIMEOUT_SECONDS
LLM_EXTRA_BODY_JSON
LLM_SYSTEM_PROMPT
```

## Run

Terminal 1:

```powershell
python start_services.py
```

Terminal 2:

```powershell
python main.py --seconds 5 --language Chinese
```

Without TTS:

```powershell
python main.py --seconds 5 --language Chinese --no-tts
```

Use an existing audio file:

```powershell
python main.py --audio-path .\last_recording.wav --language Chinese --no-tts
```

## Start One Module

```powershell
python -m app.modules.recorder.api --port 8010
python -m app.modules.asr.api --port 8000
python -m app.modules.llm.api --port 8020
python -m app.modules.tts.api --port 8030
python -m app.modules.memory.api --port 8040
```

## Health Checks

```powershell
curl http://127.0.0.1:8010/health
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8020/health
curl http://127.0.0.1:8030/health
curl http://127.0.0.1:8040/health
```

## Add More Modules

1. Add request/response models in `app/core/schemas.py`.
2. Add a new API module under `app/modules/<name>/api.py`.
3. Add default service URL config in `app/core/config.py`.
4. Call the new module from `main.py`.
