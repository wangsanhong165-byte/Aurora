# 语音助手 · Voice Agent

本地语音智能体：**持续监听 → ASR识别 → LLM流式 → TTS合成 → 播放**

## 数据流

```
麦克风 → VAD检测 → 录音 → ASR(Qwen3-ASR) → DeepSeek SSE流式
                                            → 句缓冲 → TTS(Qwen3TTS) → 播放
```

## 目录

```
ai/
├── run.py                    # 一键启动
├── .env                      # 配置
├── app/
│   ├── agent/
│   │   ├── loop.py           # 主循环
│   │   └── orchestrator.py   # ASR→LLM→TTS→Player
│   ├── core/                 # 配置/状态/事件总线
│   ├── input/
│   │   ├── manager.py        # VAD+录音
│   │   ├── recorder.py
│   │   ├── vad.py            # Silero VAD
│   │   └── interrupt.py
│   ├── modules/
│   │   ├── asr/api.py        # ASR服务 :8000
│   │   ├── llm/api.py        # LLM服务 :8020
│   │   ├── tts/api.py        # TTS服务 :8030
│   │   └── memory/api.py     # 记忆服务 :8040
│   ├── tts/player.py         # 异步播放队列
│   ├── memory/               # 短期记忆/压缩
│   └── ui/                   # TUI面板 --ui
├── models/
│   ├── asr/                  # Qwen3-ASR
│   └── tts/                  # Qwen3TTS / GSVI
├── recordings/               # 录音 + 参考音频
└── scripts/                  # GSVI启动脚本
```

## 快速开始

```powershell
pip install -r requirements.txt
python run.py
```

启动后自动拉起 ASR/LLM/TTS/Memory 四个服务，麦克风持续监听。

## 状态机

```
IDLE → LISTENING → RECORDING → PROCESSING → SPEAKING → IDLE
```

## 模型

| 模块 | 模型 | 端口 |
|------|------|------|
| ASR | Qwen3-ASR 1.7B | :8000 |
| LLM | DeepSeek v4-flash (SSE流式) | :8020 |
| TTS | Qwen3TTS 1.7B Base + 阿米娅声纹 | :8030 |
| Memory | JSONL 短期记忆 | :8040 |

## Git 分支

| 分支 | 说明 |
|------|------|
| v4-qwentts-final | 当前：Qwen3TTS + ThreadPool并行 + 死代码清理 |
| v4-amiya-cv-original | 原声优阿米娅声纹 |
| v3-qwentts-base-amiya | Qwen3TTS Base + 阿米娅初版 |
| main | 初始版本 |

## License

MIT
