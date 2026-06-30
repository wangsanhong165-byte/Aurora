# Monika Voice Companion

本地持续型 AI 陪伴：**语音/文本输入 → Brain 决策中心 → 流式回复 → TTS 合成 → 播放 / Live2D 前端**

当前分支：`v1.6-beta`

---

## 数据流

```
语音输入 → VAD检测 → 录音 → ASR(Qwen3-ASR) → Brain
文本输入 ───────────────────────────────────→ Brain
                                              │
                                ┌─→ 流式输出 → TTS(GSVI v2Pro) → 播放器
                                │
Brain (LLM + tools + memory) ───┤
                                │
                                ├─→ 工具调用 (MCP / 内置)
                                ├─→ 记忆管线 → 编译 → memory.md
                                └─→ WebSocket → Live2D 前端 (:9528)
```

---

## 目录结构

```
ai/
├── run.py                           # 一键启动 (VAD/单轮/TUI/纯文本)
├── .env                             # 配置
├── config/
│   ├── mcp_servers.json             # MCP 服务器配置
│   ├── live2d_models.json           # Live2D 表情映射
│   └── characters/                  # 角色卡片
│       └── monika/character.json    # Monika 角色定义
├── app/
│   ├── agent/loop.py                # AgentLoop: 输入收集
│   ├── brain/                       # Brain 决策中心 + prompt builder
│   ├── bridge/server.py             # Live2D Bridge — Web 服务 + WebSocket API
│   ├── core/                        # 基础设施 (config, event_bus, state, 事件)
│   ├── runtime/                     # TurnRuntime, ChatPipeline, AgentRuntime
│   ├── input/                       # VAD + 录音 + 打断检测
│   ├── tts/player.py                # 异步播放队列
│   ├── models/                      # LLM/ASR/TTS 协议接口 + HTTP 实现
│   ├── memory/                      # SQLite+FTS5 记忆存储 + 抽取 + 编译
│   ├── character/                   # 角色注册 + 导入
│   ├── initiative/                  # 主动对话引擎
│   ├── screen/                      # Windows 窗口监控
│   ├── tools/                       # 工具注册 + 内置工具
│   ├── mcp/                         # MCP 工具系统 (Python SDK)
│   ├── modules/                     # 微服务模块
│   │   ├── asr/api.py               # ASR 服务 (:8000)
│   │   ├── llm/api.py               # LLM 服务 (:8020)
│   │   ├── tts/api.py               # TTS 服务 (:8030)
│   │   ├── memory/api.py            # 记忆服务 (:8040)
│   │   ├── memory_compiler.py       # 四段记忆编译管线
│   │   ├── mcp/                     # MCP 模块 (bridge 集成用)
│   │   ├── sentence_divider.py      # TTS 长文本切分器
│   │   └── ...
│   └── prompts/utils/               # 提示词模板文件
│       ├── identity_ishiki.txt
│       ├── character_setting.txt
│       ├── pinned_memories.txt
│       ├── role_setting.txt
│       ├── available_emotions.txt
│       ├── thought_protocol.txt
│       └── output_format.txt
├── frontend/                        # Electron + React + Vite + Chakra UI
│   ├── src/                         # 前端源码
│   └── dist/                        # 构建产物
├── models/                          # Live2D 模型 + TTS 模型权重
├── data/                            # 运行时数据
│   └── memory/
│       ├── memory.db                # SQLite 记忆存储
│       ├── compiled/                # per-character 编译记忆
│       └── histories/               # 会话历史 (JSON)
├── scripts/start_bridge.py          # 全服务启动脚本
├── start_web.bat                    # Windows 一键启动
└── requirements.txt
```

---

## 快速开始

```powershell
pip install -r requirements.txt

# --- CLI 模式 ---
python run.py                         # VAD 持续语音 (默认)
python run.py --text                  # 纯文字聊天
python run.py --no-vad                # 单轮定长录音

# --- TUI 面板 ---
python run.py --ui tui

# --- Web/Live2D 模式 ---
python scripts/start_bridge.py        # 启动后台服务 + bridge
# 或双击 start_web.bat
# 打开 http://127.0.0.1:9528
```

启动后自动拉起 ASR/LLM/TTS/Memory/GSVI 五个服务，进入持续监听。

---

## 核心架构

### 设计原则

- **单一 Brain**: 系统只有一个决策中心 (`app/brain/`)。Memory/State/Character 只存数据不做决策。
- **事件驱动**: 输入 → EventBus → Brain → 输出事件，模块间通过事件通信。
- **记忆不阻塞对话**: 日志同步写入，提取/压缩/合并/索引走后台。
- **角色无关**: 记忆管线接受 `character_name` 参数，切换角色自动重新编译。

### 模块分类

| 类别 | 模块 |
|------|------|
| **输入源** | 语音 (VAD)、键盘文本、屏幕监控、定时器、WebSocket |
| **状态层** | 记忆 (memory.db)、角色 (character/)、项目状态 |
| **决策层** | Brain (唯一推理和决策中心) |
| **执行层** | TTS 播放、Live2D 动画、MCP 工具、通知 |

### 输入路径

| 输入方式 | 路径 |
|---------|------|
| 语音 VAD | AgentLoop → InputManager → TurnRuntime.process_audio() → ASR → Brain |
| 文字 | AgentLoop → TurnRuntime.process_text() → Brain |
| Web (浏览器) | Bridge WebSocket → LLM → TTS → audio stream |
| 主动触发 | InitiativeChecker → Queue → Brain → TTS → Player |

### 状态机

```
IDLE → LISTENING → RECORDING → PROCESSING → SPEAKING → IDLE
                                      ↓ (可选)
                                 工具调用循环 (最多5轮)
```

---

## 核心组件

### Bridge Web 服务器 (`:9528`)

FastAPI + WebSocket 双协议，提供：
- **Web 前端** — 静态文件服务 (Electron/React 构建产物)
- **Live2D 模型** — `.model3.json` / `.moc3` / 纹理文件服务
- **WebSocket API** — 实时语音/文本交互
- **REST API** — 固定记忆 CRUD、历史记录、健康检查

#### WebSocket 协议

| 消息类型 (客户端 → 服务器) | 说明 |
|---|---|
| `text-input` | 文本输入 |
| `mic-audio-data` | 麦克风音频块 (float32 PCM) |
| `mic-audio-end` | 录音结束，触发处理 |
| `ai-speak-signal` | 主动发言触发 (含 idle_time) |
| `ping` | 心跳 |
| `fetch-history-list` | 获取历史列表 |
| `fetch-and-set-history` | 加载指定历史 |
| `create-new-history` | 新建历史 |
| `delete-history` | 删除历史 |
| `switch-character` | 运行时切换角色 |
| `reload-prompts` | 热重载提示词模板 |

| 消息类型 (服务器 → 客户端) | 说明 |
|---|---|
| `conversation-chain-start/end` | 对话阶段标记 |
| `user-input-transcription` | ASR 识别文本 |
| `full-text` | Live2D 显示文本 |
| `audio` | TTS 音频 (base64) + 表情 |
| `expression` | Live2D 表情指令 |
| `history-list` / `history-data` | 历史数据 |
| `character-switched` | 角色切换确认 |

#### Bridge 特有功能

- **内心独白 (Thought Protocol)** — LLM 在 JSON 中输出 `thought` 字段，表示内心活动，不会被用户看到。
- **分段输出** — LLM 返回 `segments` 数组，每段可附带不同 tone 表情，依次 TTS + 动画。
- **情绪检测兜底** — LLM 未识别情绪时，通过关键词匹配 fallback tone。
- **固定记忆** — 字符设定之外的持久记忆，存储在 `pinned.md`，通过前端设置面板编辑。
- **会话历史** — JSON 文件存储，前端历史面板浏览/切换/删除。

### LLM (DeepSeek)

- `deepseek-v4-flash` (OpenAI 兼容 API)
- 支持 function calling (tool_calls)
- 支持 streaming 和非流式两种模式
- JSON 模式输出 (segments + thought + final_reply)

### MCP 工具系统

两层架构 — Brain 层 (`app/mcp/`) 和 Bridge 层 (`app/modules/mcp/`)。

Bridge 层配置于 `config/mcp_servers.json`：

| 服务器 | 工具 | 说明 |
|--------|------|------|
| `time` | `mcp-server-time` | 获取当前时间 (Asia/Shanghai) |
| `ddg-search` | `duckduckgo-mcp-server` | DuckDuckGo 网页搜索 |

MCP 工具通过 OpenAI function calling 协议集成到 LLM 交互循环：
1. LLM 调用 → 检测 `tool_calls`
2. 通过 MCP 协议执行工具 (stdio)
3. 结果追加回 messages
4. LLM 整合工具结果生成最终回复
5. 最多 5 轮工具循环

添加新工具只需编辑 `mcp_servers.json`：

```json
{
  "mcp_servers": {
    "new-tool": {
      "command": "uvx",
      "args": ["mcp-server-package-name"]
    }
  }
}
```

### 记忆系统

两层记忆：

| 层级 | 存储 | 说明 |
|------|------|------|
| **实时** | SQLite + FTS5 | 对话日志、事实、全文搜索 |
| **编译** | memory.md (四段) | 后台管线：滚动摘要 → 事实提取 → 编译 |
| **会话历史** | JSON 文件 | 前端可浏览/切换的对话历史 |

后台编译管线每 5 轮对话或日期变更时触发，语言自适应（中文/英文/日文）。

### 提示词文件系统

系统提示词拆分为独立文件存储于 `app/prompts/utils/`，通过 `loader.py` 按名加载渲染。支持热重载（发送 `reload-prompts` WebSocket 消息）。

---

## 配置

### 服务端口

| 服务 | 端口 | 模型 |
|------|------|------|
| ASR | `:8000` | Qwen3-ASR 1.7B |
| LLM | `:8020` | DeepSeek v4-flash |
| TTS | `:8030 / :8050` | GSVI v2Pro nvidia50 |
| Memory | `:8040` | SQLite+FTS5 |
| Bridge | `:9528` | FastAPI + Live2D Web |

### 环境变量

| 变量 | 说明 | 默认 |
|------|------|------|
| `ASR_ENGINE` | ASR 引擎 | `qwen3-asr` |
| `TTS_ENGINE` | TTS 引擎 | `gsvi-v2pro` |
| `LLM_MODEL` | LLM 模型名 | `deepseek-v4-flash` |
| `LLM_BASE_URL` | LLM API 地址 | `https://api.deepseek.com` |
| `DEEPSEEK_API_KEY` | LLM API 密钥 | - |
| `ACTIVE_CHARACTER` | 默认角色 | `monika` |
| `START_GSVI` | 启动 GSVI v2Pro | `true` |
| `SCREEN_ENABLED` | 屏幕监控 | `0` |
| `INITIATIVE_IDLE_SEC` | 空闲主动触发 (秒) | `300` |
| `LLM_REASONING_EFFORT` | 推理强度 | `medium` |

---

## 角色系统

角色卡存储在 `config/characters/<id>/character.json`，包含：

- **identity** — 结构化身份描述（你是谁）
- **ishiki** — 结构化行为规则（你怎么待人接物）
- **character_setting** — 扁平设定（identity/ishiki 不存在时的 fallback）
- **tts** — TTS 引擎、声纹参考音频、prompt 语言
- **live2d** — 表情映射配置

切换角色通过 WebSocket 消息 `switch-character` 实现热切换，无需重启。

---

## 工具链

| 工具 | 用途 |
|------|------|
| `python run.py` | 一键启动 CLI 模式 |
| `python run.py --ui tui` | 启动 TUI 面板 |
| `python scripts/start_bridge.py` | 启动 Web 模式 (后台服务 + bridge) |
| `start_web.bat` | Windows 一键 Web 模式 |
| `python run.py --text` | 纯文字聊天模式 |

---

## Git 分支

| 分支 | 说明 |
|------|------|
| **v1.6-beta (当前)** | 角色系统重构，Live2D bridge，多引擎 TTS，Web 前端，MCP 工具，记忆编译 |
| v1.5-final | Live2D 适配 + 水印修复 + 架构优化 |
| v1.4 | 情绪回复 + 主动对话 + 流式 TTS |
| v1.3-final | 主动对话引擎、情景记忆、关系系统 |
| v1.2 | GSVI v2Pro TTS、统一 TurnRuntime、流式管线 |
| v1.1-final | GSVI TTS、时间戳日志 |
| main | 初始版本 |

---

## License

MIT
