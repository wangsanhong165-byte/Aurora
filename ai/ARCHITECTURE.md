# 项目架构宪法 (Architecture Constitution)

> 这不是功能文档，是架构边界宪法。以后所有 AI Code / Codex / Claude Code / Cursor 都必须先读这一份。

---

## 一、项目定位

**构建一个长期陪伴型 AI，而非角色聊天平台。**

核心价值：长期陪伴 · 长期记忆 · 主动交互 · 项目协助 · 自然语音

---

## 二、架构总图（只看三张图）

### 图1：总架构

```
                       ┌─────────────┐
                       │   State     │ ← Activity / Attention / Emotion / Context
                       └──────┬──────┘
                              │ reads
                              ▼
┌────────┐   Event    ┌──────────────┐   Event    ┌────────┐
│ Input  │ ────────►  │    Brain     │ ────────►  │ Output │
│ (ASR)  │            │  (唯一决策)   │            │ (TTS)  │
└────────┘            └──┬───┬───┬───┘            └────────┘
                         │   │   │
              ┌──────────┘   │   └──────────┐
              ▼              ▼              ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │  Memory  │  │  Tools   │  │ Project  │
        │(后台异步) │  │(插件路由) │  │(项目记忆) │
        └──────────┘  └──────────┘  └──────────┘
```

**核心原则**：所有模块只和 Event Bus 说话，不直接互相调用。

### 图2：记忆流

```
Conversation (Raw Log)
      │
      ▼
┌──────────────┐
│  Extractor   │ ← LLM 提取事实/摘要（后台异步，不阻塞回复）
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Candidate   │
│  Memory      │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Merger     │ ← 去重/合并/更新
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Long-Term   │ ← JSONL 主存储（不是向量库）
│  Memory      │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Vector Index │ ← 只是索引，可重建
└──────────────┘
```

**关键**：Vector Index 不是主存储，只是索引。

### 图3：主动性流

```
Screen Monitor / Timer / StateChange / ToolEvent
      │
      ▼
┌───────────────┐
│ Event Queue   │
└───────┬───────┘
        │
        ▼
┌───────────────┐
│    Brain      │ ← 唯一决策点
└───────┬───────┘
        │
        ▼
   Should Speak?
     Yes / No
```

**铁律**：ScreenWatcher / Timer / Plugin 永远不直接调 LLM。

---

## 三、六层架构

### 第一层：决策层（Brain）

- **唯一入口**：所有用户输入、主动事件、工具结果都只进 Brain
- **Brain 不执行**：Brain 只做 Reasoning / Planning / Memory Decision / Tool Decision
- Brain 调用下层协议，不调用具体实现

### 第二层：记忆层（Memory）

- **三层存储**：ShortTerm（窗口对话）→ Candidate（待确认记忆）→ LongTerm（持久卡片）
- **后台异步**：记忆提取和整理绝不阻塞对话回复
- **主存储是 JSONL**，向量索引可重建

### 第三层：主动层（Initiative）

- 事件源 → 队列 → Brain → Speak?
- 所有外部事件（屏幕变化/定时器/状态变更）统一进入队列
- Brain 结合 State 决定是否说话

### 第四层：状态层（State）

- Activity / Attention / Emotion / Device / Context
- 状态是事实，不是决策
- 主动性先看 State，再决定说/不说

### 第五层：模型层（Adapters）

```
LLMAdapter    → OpenAI / DeepSeek / Gemini / Local
TTSAdapter    → GSVI / QwenTTS / EdgeTTS
ASRAdapter    → Whisper / QwenASR / FunASR
VisionAdapter → 屏幕分析 / 图像理解
```

**业务层永远不知道 "DeepSeek" 这个名字，只知道 `llm.generate()`**

### 第六层：插件层（Plugins）

```
Brain → ToolRouter → Plugin → ToolResult → Brain
```

- 统一 Tool Request / Tool Result 格式
- 插件注册、权限控制、分组开关

---

## 四、目录结构

```
app/
├── core/           # 事件总线、状态、配置
│   ├── events.py
│   ├── event_bus.py
│   ├── state.py
│   └── config.py
│
├── brain/          # 唯一决策中心
│   └── service.py
│
├── runtime/        # 执行层（AgentRuntime / Turn / Pipeline）
│   ├── agent_runtime.py
│   ├── turn.py
│   └── pipeline.py
│
├── memory/         # 记忆系统（后台异步）
│   ├── short_term.py
│   ├── long_term.py
│   ├── background.py
│   ├── extractor.py
│   └── summarizer.py
│
├── models/         # 模型适配器
│   ├── adapters.py
│   └── http_adapters.py
│
├── character/      # 角色系统
│   ├── registry.py
│   └── loader.py
│
├── tools/          # 工具系统
│   ├── registry.py
│   └── builtins/
│
├── input/          # 输入层（VAD / 录音）
├── tts/            # TTS 播放层
├── initiative/     # 主动队列
├── project/        # 项目记忆
├── screen/         # 屏幕监控
└── ui/             # TUI 面板
```

---

## 五、开发铁律

1. **模块只和 Bus 说话，不直接互相调用**
2. **所有 LLM 调用只走 Brain**
3. **记忆操作不阻塞对话回复**
4. **业务代码只依赖 Adapter 协议，不依赖具体模型名**
5. **新功能 = 注册事件 + 挂到 Bus，不改旧模块**
6. **Vector Index 可重建，LongTermMemory 是主存储**

---

## 六、禁止清单

- ❌ ScreenWatcher 直接调 LLM
- ❌ Timer 直接调 LLM
- ❌ 模块 A import 模块 B 只为调一个方法
- ❌ 在对话主链路上做记忆提取
- ❌ 硬编码模型名称到业务逻辑
- ❌ 出现 `_v2.py` / `_new.py` / `_final.py` 文件

---

*最后更新：2026-06-06*
