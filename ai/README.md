# 语音助手 · Voice Agent v1

本地语音智能体，支持 **持续监听 → 语音识别 → 流式大模型 → 句级语音合成 → 异步播放** 的低延迟流水线。

## 架构概览

```
┌─────────────────────────────────────────────────────────┐
│                      run.py (一键启动)                   │
├─────────────────────────────────────────────────────────┤
│  AgentLoop                                              │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐            │
│  │ Input    │→  │ Orches-  │→  │ Player   │            │
│  │ Manager  │   │ trator   │   │ (async)  │            │
│  │ VAD 监听  │   │ 流水线编排│   │ 非阻塞播放 │           │
│  └──────────┘   └──────────┘   └──────────┘            │
│       ↓               ↓                                │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐            │
│  │ ASR Svc  │   │ LLM Svc  │   │ TTS Svc  │            │
│  │  :8000   │   │  :8020   │   │  :8030   │            │
│  │Qwen3-ASR │   │DeepSeek  │   │  GSVI    │            │
│  └──────────┘   │ (SSE流式) │   │  :8050   │            │
│                 └──────────┘   └──────────┘            │
│  ┌──────────┐                                          │
│  │ Memory   │  ┌──────────┐   ┌──────────┐             │
│  │  :8040   │  │Event Bus │   │ TUI Panel│             │
│  │JSONL存储  │  │ 事件驱动  │   │ (--ui)   │             │
│  └──────────┘  └──────────┘   └──────────┘             │
└─────────────────────────────────────────────────────────┘
```

## 数据流（单轮对话）

```
麦克风 → VAD检测语音 → 录音(WAV)
  → ASR服务 (Qwen3-ASR-1.7B) → 文本
  → LLM服务 SSE流式 (DeepSeek stream=True)
      ──token流──→ 句缓冲 (。！？切句)
          ──逐句──→ GSVI 语音合成
              ──WAV──→ AsyncAudioPlayer (后台播放)
```

**低延迟关键设计：**
- LLM 流式输出，不等全文
- 句子缓冲：遇到标点立即切句送 TTS
- TTS 逐句合成 + 异步播放器，第一句出来就播
- 用户再说话 → `player.stop()` 立刻打断

## 目录结构

```text
ai/
├── run.py                       # 一键启动入口
├── .env                         # 环境变量配置
├── app/
│   ├── agent/
│   │   ├── loop.py              # AgentLoop 主循环
│   │   ├── orchestrator.py      # 流水线编排 (ASR→LLM→TTS→Player)
│   │   └── actions.py           # 动作定义
│   ├── core/
│   │   ├── config.py            # 路径、服务URL、.env 加载
│   │   ├── state.py             # 状态机 (IDLE/LISTENING/PROCESSING/SPEAKING)
│   │   ├── event_bus.py         # 线程安全事件总线
│   │   └── schemas.py           # Pydantic 数据模型
│   ├── input/
│   │   ├── manager.py           # 输入管理 (VAD + 录音)
│   │   ├── recorder.py          # 录音模块
│   │   ├── vad.py               # webrtcvad 封装
│   │   └── interrupt.py         # 打断检测 (RMS能量)
│   ├── modules/
│   │   ├── asr/api.py           # Qwen3-ASR HTTP 服务 (:8000)
│   │   ├── llm/api.py           # LLM HTTP 服务 + SSE流式端点 (:8020)
│   │   ├── tts/api.py           # TTS HTTP 服务 (GSVI/pyttsx3) (:8030)
│   │   └── memory/api.py        # 记忆 HTTP 服务 (:8040)
│   ├── asr/                     # 伪流式 ASR 模块 (可选增强)
│   ├── tts/
│   │   └── player.py            # 异步音频播放队列
│   ├── memory/
│   │   ├── short_term.py        # 短期记忆
│   │   ├── long_term.py         # 长期记忆
│   │   ├── summarizer.py        # 记忆压缩
│   │   └── profile.py           # 用户画像
│   └── ui/                      # Textual TUI 控制面板
├── models/
│   ├── asr/Qwen3-ASR-1.7B/      # 语音识别模型
│   └── tts/                     # TTS 模型
└── legacy/                      # 旧版脚本归档
```

## 环境要求

- Windows + Python 3.12+
- CUDA 12.8 (RTX 显卡) 或 CPU
- 麦克风

## 快速开始

### 1. 安装依赖

```powershell
pip install -r requirements.txt
```

### 2. 配置 .env

```ini
# LLM (DeepSeek)
DEEPSEEK_API_KEY=你的Key
LLM_MODEL=deepseek-v4-flash
LLM_REASONING_EFFORT=medium

# TTS (GSVI)
TTS_ENGINE=gsvi
GSVI_VOICE=明日方舟-中文-阿米娅
```

### 3. 启动

```powershell
# 持续监听模式
python run.py

# 带 TUI 控制面板
python run.py --ui

# 单轮模式 (固定时长录音)
python run.py --no-vad --seconds 5
```

启动后自动拉起所有微服务：
- GSVI TTS → `:8050`
- ASR → `:8000`
- LLM → `:8020`
- TTS → `:8030`
- Memory → `:8040`

## 状态机

```
IDLE → LISTENING → RECORDING → PROCESSING → SPEAKING → IDLE
                                                    ↓ (用户打断)
                                              player.stop()
```

## 可选模块

| 模块 | 说明 | 状态 |
|---|---|---|
| `/v1/llm/chat/stream` | LLM SSE 流式端点 | ✅ 已集成 |
| `app/tts/player.py` | 异步播放队列 | ✅ 已集成 |
| `app/asr/` | 伪流式 ASR (边说边识别) | 📦 可选 |
| `app/ui/` | Textual TUI (`--ui`) | ✅ 可用 |


## Git 分支概览

| 分支 | 说明 |
|---|---|
| codex/v1-stable-milestone | P0-P2 优化完成，低延迟流水线稳定里程碑 |
| codex/v1-optimized | P0-P2 TTS并行 + 静音0.7s + Player修复 |
| codex/v1-low-latency-streaming | SSE流式LLM + 句缓冲TTS + 异步播放器 |
| codex/v1-pseudo-streaming-asr | 伪流式ASR（chunk增量识别） |
| codex/v1-input-state-machine | v1输入状态机 + Textual TUI |
| codex/v1-architecture | v1架构升级（事件驱动） |
| codex/v1-tui-stable | TUI控制面板稳定版 |
| codex/stable-voice-pipeline | 早期稳定语音管道（HTTP微服务串联） |
| main | 初始版本 |

## License

MIT
