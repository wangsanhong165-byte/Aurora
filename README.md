[README.md](https://github.com/user-attachments/files/28417648/README.md)
# 语音助手 · Voice Assistant

基于微服务架构的本地语音助手，支持 **语音识别 → 大模型对话 → 语音合成** 完整流水线。

## 功能特性

- **本地 ASR**：Qwen3-ASR 离线语音识别，支持中英文
- **云端 LLM**：接入 DeepSeek / OpenAI 等 OpenAI 兼容接口
- **本地 TTS**：GPT-SoVITS 高质量语音合成（可切换 pyttsx3 降级）
- **VAD 语音检测**：持续监听，检测到说话才录音，说完自动停
- **短期记忆**：JSONL 格式对话记忆，支持上下文连续对话
- **微服务架构**：各模块独立部署，可单独启停

## 架构

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ Recorder │ →  │   ASR    │ →  │   LLM    │ →  │   TTS    │ →  │  Memory  │
│  :8010   │    │  :8000   │    │  :8020   │    │  :8030   │    │  :8040   │
│ 麦克风录音 │    │ 语音转文字 │    │ 云端大模型 │    │ 语音合成  │    │ 短期记忆  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
      │                                                              │
      └─────────────────── main.py 编排 ─────────────────────────────┘
```

## 目录结构

```text
ai/
├── main.py                  # 流水线编排器（入口）
├── start_services.py        # 一键启动所有微服务
├── voice_agent.py           # 独立版（不依赖微服务）
├── requirements.txt         # Python 依赖
├── app/
│   ├── core/
│   │   ├── config.py        # 默认路径、服务URL、.env 加载
│   │   └── schemas.py       # 请求/响应数据模型
│   └── modules/
│       ├── recorder/api.py  # 麦克风录音 + VAD 语音检测
│       ├── asr/api.py       # Qwen3-ASR 语音识别
│       ├── llm/api.py       # DeepSeek/OpenAI 大模型适配
│       ├── tts/api.py       # GPT-SoVITS / pyttsx3 语音合成
│       └── memory/api.py    # 短期对话记忆
├── GPT-SoVITS-1007-cu128/   # GPT-SoVITS 引擎（需单独部署）
├── Qwen3-ASR-1.7B/          # 语音识别模型（需下载）
└── tts_outputs/             # 合成的音频文件
```

## 环境要求

- Python 3.12
- CUDA 12.8（RTX 5060）或 CPU 模式
- 麦克风

## 安装

### 1. 创建虚拟环境

```powershell
conda create -n voice python=3.12 -y
conda activate voice
python -m pip install --upgrade pip
```

### 2. 安装 PyTorch（CUDA 12.8）

```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```

### 3. 安装项目依赖

```powershell
pip install -r requirements.txt
```

### 4. 配置环境变量

复制 `.env.example` 为 `.env`，填入你的 API Key：

```powershell
Copy-Item .env.example .env
```

`.env` 关键配置：

```ini
# ── 大模型配置（以 DeepSeek 为例）──
LLM_API_KEY_ENV=DEEPSEEK_API_KEY
DEEPSEEK_API_KEY=你的Key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash

# ── TTS 配置 ──
TTS_ENGINE=gsvi               # gsvi 或 pyttsx3
GSVI_URL=http://127.0.0.1:8050
GSVI_MODEL=GSVI-v4
GSVI_VOICE=                   # 留空自动检测
```

### 5. 部署 GPT-SoVITS（可选）

如果使用 GSVI 语音合成，需先启动 GSVI 服务：

```powershell
python start_services.py --with-gsvi
```

## 使用方式

### 单轮对话

```powershell
python main.py
```

### 连续对话（手动确认）

```powershell
python main.py --loop
```

每轮说完按回车继续，输入 `q` 退出。

### VAD 持续监听（推荐）

```powershell
python main.py --vad
```

无需按键，开口说话即自动触发，说完停顿 1.5 秒自动结束。连续 10 轮无语音自动退出。

```powershell
# 自定义参数
python main.py --vad --vad-silence-timeout 2.0 --vad-max-duration 60

# 限制轮数
python main.py --vad --turns 20
```

### 更多选项

| 参数 | 说明 | 默认值 |
|---|---|---|
| `--seconds` | 固定录音时长（秒） | 5.0 |
| `--language` | ASR 语言 | Chinese |
| `--no-tts` | 关闭语音合成，只打印文字 | — |
| `--audio-path` | 跳过录音，直接识别文件 | — |
| `--loop` | 连续对话模式（手动回车） | — |
| `--vad` | VAD 持续监听模式 | — |
| `--vad-silence-timeout` | 沉默多久后停止录音（秒） | 1.5 |
| `--vad-max-duration` | 最大录音时长（秒） | 30 |
| `--turns` | 最大对话轮数 | 0=无限 |
| `--tts-engine` | TTS 引擎：gsvi / pyttsx3 | gsvi |
| `--tts-voice` | 指定语音角色名 | 自动检测 |
| `--memory-limit` | 传给 LLM 的记忆条数 | 8 |

### 单独启动某个服务

```powershell
python -m app.modules.recorder.api  --port 8010
python -m app.modules.asr.api       --port 8000
python -m app.modules.llm.api       --port 8020
python -m app.modules.tts.api       --port 8030
python -m app.modules.memory.api    --port 8040
```

### 健康检查

```powershell
curl http://127.0.0.1:8010/health
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8020/health
curl http://127.0.0.1:8030/health
curl http://127.0.0.1:8040/health
```

## 切换到其他大模型

修改 `.env` 即可，支持所有 OpenAI 兼容接口：

```ini
# 切换到 OpenAI
LLM_API_KEY_ENV=OPENAI_API_KEY
OPENAI_API_KEY=sk-xxx
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4.1-mini
LLM_REASONING_EFFORT=
LLM_THINKING_TYPE=none
```

## 扩展模块

1. 在 `app/core/schemas.py` 添加数据模型
2. 在 `app/modules/<name>/api.py` 新建 API 模块
3. 在 `app/core/config.py` 添加默认 URL
4. 在 `main.py` 中调用新模块
