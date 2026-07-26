# Monika Voice Companion

本地持续型 AI 陪伴 — 语音/文本交互，实时 TTS 语音合成，Live2D 动画前端。

---

## 项目简介

Monika Voice Companion 是一个运行在 Windows 上的本地 AI 语音陪伴系统。它通过麦克风或文本接收用户输入，经过 LLM 推理、记忆检索、情绪分析，最终以语音合成 + Live2D 动画的方式回应用户。

核心能力：
- **语音交互** — VAD 检测、ASR 识别、TTS 语音合成
- **持久记忆** — SQLite+FTS5 记忆存储，后台编译管线
- **Live2D 动画** — 表情、动作、唇同步
- **主动对话** — 空闲检测、屏幕监控触发主动关怀
- **工具使用** — MCP 工具系统（搜索、时间等）

---

## 环境要求

| 依赖 | 版本要求 |
|------|---------|
| Python | ≥ 3.10 |
| OS | Windows 10/11 |
| GPU (推荐) | NVIDIA 50 系列 (GSVI v2Pro TTS 优化) |
| 麦克风 | 必需 (语音模式) |

### 外部服务

系统自动启动以下微服务：

| 服务 | 端口 | 用途 |
|------|------|------|
| ASR | :9101 | Qwen3-ASR 语音识别 |
| LLM | :9102 | OpenAI-compatible LLM API |
| TTS | :9103 | TTS 统一入口 |
| Memory | :9104 | SQLite+FTS5 记忆服务 |
| GSVI | :9105 | GPT-SoVITS v2Pro |
| Bridge | :9528 | Web 服务 + WebSocket API |

---

## 快速开始

### 1. 安装依赖

```powershell
pip install -r requirements.txt
```

### 2. 配置

复制 `.env.example` 为 `.env`，填写以下必要配置：

```
DEEPSEEK_API_KEY=your_api_key_here
```

### 3. 运行

```powershell
# CLI 语音模式 (VAD 持续监听)
python run.py

# 纯文字聊天模式
python run.py --text

# 单轮定长录音模式
python run.py --no-vad

# TUI 面板模式
python run.py --ui tui

# Web/Live2D 全功能模式
python scripts/start_bridge.py
# 或双击 start_web.bat
# 打开 http://127.0.0.1:9528
```

启动后自动拉起 ASR/LLM/TTS/Memory/GSVI 五个服务，进入持续监听。

---

## 使用说明

### 语音模式 (默认)

1. 运行 `python run.py`
2. 程序自动检测麦克风，进入 VAD 监听
3. 说话后自动录音 → ASR 识别 → LLM 推理 → TTS 合成 → 播放
4. 空闲 5 分钟后自动触发主动对话

### 文本模式

```powershell
python run.py --text
```

在终端输入文字，按 Enter 发送。

### Web/Live2D 模式

```powershell
python scripts/start_bridge.py
```

在浏览器打开 `http://127.0.0.1:9528`，使用带 Live2D 动画的图形界面。

---

## 环境变量

| 变量 | 说明 | 默认 |
|------|------|------|
| `ASR_ENGINE` | ASR 引擎 | `qwen3-asr` |
| `TTS_ENGINE` | TTS 引擎 | `gsvi-v2pro` |
| `LLM_MODEL` | LLM 模型名 | `deepseek-v4-flash` |
| `LLM_BASE_URL` | LLM API 地址 | `https://api.deepseek.com` |
| `DEEPSEEK_API_KEY` | LLM API 密钥 | — |
| `ACTIVE_CHARACTER` | 默认角色 | `monika` |
| `START_GSVI` | 启动 GSVI v2Pro | `true` |
| `SCREEN_ENABLED` | 屏幕监控 | `0` |
| `INITIATIVE_IDLE_SEC` | 空闲主动触发间隔 | `300` |
| `LLM_REASONING_EFFORT` | 推理强度 | `medium` |

---

## 开发

### 项目结构

```
ai/
├── ARCHITECTURE.md               # 项目架构文档
├── run.py                         # 启动入口
├── .env                           # 配置文件
├── app/                           # Python 后端
├── frontend/                      # Electron + React + Vite 前端
├── config/                        # 角色配置、模型映射
├── models/                        # Live2D 模型文件
├── data/                          # 运行时数据 (记忆、历史)
├── start_web.bat                  # Windows 一键启动
└── requirements.txt
```

### 架构文档

详细架构、模块职责、数据流说明请见：

→ **[ARCHITECTURE.md](ARCHITECTURE.md)**

Runtime V3 的唯一交互入口是 `CharacterRuntime.handle_turn(TurnInput)`；
前端只通过 `/client-ws` 使用 V2 类型化 Transport 协议，并统一进入 Runtime V3。

---

## License

MIT
