# Companion Runtime — Architecture v2

> Companion Runtime 是系统唯一执行核心。所有交互（用户输入、主动行为、视觉、工具回调等）统一表示为 Event，由 Runtime 调度，通过 Character 驱动决策，经由 Interface 调用可替换的 Provider，最终作用于外部世界。

---

## Status

| 状态 | 含义 |
|------|------|
| **Current** | 现在真实运行的样子 |
| **Target** | 未来想变成的样子 |
| **Migration** | 从 Current 到 Target 的路径 |

本文档描述 **Target**。必要时标注 Current 状态和 Migration 步骤。

---

## 一、宪法（Constitution）

### 第一条 — Runtime 是唯一执行入口

所有交互（语音输入、文本输入、主动行为、视觉信号、工具回调、MCP 响应）统一表示为 **Event**，通过 `Runtime.dispatch(event)` 进入系统。

不存在第二条路径。不存在第二个入口。

### 第二条 — 每种能力只有一个正式接口

LLM Interface、TTS Interface、ASR Interface、Live2D Interface、Memory Interface。

Interface 是稳定契约。Interface 属于 `interfaces/` 层，不属于 Provider。

### 第三条 — 第三方项目必须通过 Integration 接入

禁止直接修改第三方代码。禁止业务逻辑进入第三方代码。

第三方项目永远不知道 Runtime 的存在。

### 第四条 — Provider 可替换

新增 DeepSeek / Claude / FishSpeech / Whisper 时，不得修改 Domain、Runtime、或 Interface。

只允许：新增 Provider 文件 → 注册 → 结束。

### 第五条 — Runtime 不依赖具体 Provider

Runtime 不知道 DeepSeek。不知道 GPT-SoVITS。不知道 Whisper。

Runtime 只通过 Interface 调用能力。

### 第六条 — Legacy 冻结

`legacy/` 目录中的代码可以被调用，但禁止新增。

Legacy 只允许删，不允许加。

### 第七条 — Brain 不是中心

Brain 不是系统核心。Brain 只是 Strategy 的组合（Planner、PromptCompiler、Reasoner）。

Runtime 才是中心。Character 是身份载体。

### 第八条 — 每项新增前回答三个问题

1. 谁调用它？
2. 它依赖谁？
3. 如果未来换实现，需要改几处？

如果答案不是**"一处"**，说明架构有问题。

---

## 二、架构总览

```
┌─────────────────────────────────────────────────────┐
│                    UI Layer                         │
│     Web / Live2D / Mobile / API / Terminal          │
└──────────────────────┬──────────────────────────────┘
                       │ Event
                       ▼
┌─────────────────────────────────────────────────────┐
│                Runtime Layer                        │
│                                                     │
│  Runtime.dispatch(event)                            │
│       │                                             │
│       └── Pipeline (ordered steps)                  │
│            ├── asr_step                             │
│            ├── memory_retrieve_step                 │
│            ├── character_step                       │
│            ├── brain_step (or decision_pipeline)    │
│            ├── tool_step                            │
│            ├── memory_save_step                     │
│            ├── emotion_step                         │
│            ├── tts_step                             │
│            └── live2d_step                          │
│                                                     │
│  Event Sources (producers, not a second Runtime):   │
│    Scheduler / Watcher / Reminder / Heartbeat       │
│         │                                           │
│         └──→ Runtime.dispatch(event)                │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              Domain Layer                           │
│                                                     │
│  Character  (Persona, Emotion, Relationship,        │
│              Preference, Goal, Initiative)          │
│                                                     │
│  Conversation / Memory / Vision / Scheduler         │
│                                                     │
│  Domain 不知道 Provider。Domain 只引用 Interface。   │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              Interface Layer                        │
│                                                     │
│  LLMInterface / TTSInterface / ASRInterface         │
│  Live2DInterface / MemoryInterface / VisionInterface│
│  ToolInterface                                      │
│                                                     │
│  + MockLLM / MockTTS / MockASR (固定回复)           │
│  + ReplayLLM / ReplayASR (回放真实请求)             │
│                                                     │
│  Interface 是稳定契约，不依赖任何第三方。            │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│             Provider Layer                          │
│                                                     │
│  LLM:    DeepSeek / Claude / OpenAI / Mock / Replay │
│  TTS:    GSVI / Edge / Qwen / FishSpeech            │
│  ASR:    SenseVoice / Whisper / Sherpa              │
│  Live2D: OpenLLMVTuberAdapter → Open-LLM-VTuber     │
│  Memory: OpenHanakoAdapter → OpenHanako (参考)      │
│                                                     │
│  ProviderRegistry (发现) + Factory (创建)           │
│                                                     │
│  Provider 实现 Interface。Adapter 是 Provider        │
│  的一种实现方式——用于包裹第三方项目。                │
└─────────────────────────────────────────────────────┘
```

---

## 三、Runtime

### 3.1 核心设计

Runtime 只有一个入口：`Runtime.dispatch(event)`。

不存在 `handle()`、`onEvent()`、`process_text()` 等多个入口。

### 3.2 Event

所有交互统一表示为 Event：

| Event | 来源 | 说明 |
|-------|------|------|
| `SpeechReceived` | 麦克风/VAD | 用户语音输入 |
| `TextReceived` | 键盘/API | 用户文本输入 |
| `InitiativeTriggered` | Scheduler | 主动聊天触发 |
| `VisionUpdated` | 屏幕/摄像头 | 视觉信息到达 |
| `ToolFinished` | Tool Provider | MCP 工具执行完成 |
| `SessionResumed` | 系统 | 会话恢复 |

每个 Event 包含：

```python
@dataclass
class Event:
    type: str
    payload: dict
    source: str
    timestamp: float
    id: str
```

### 3.3 Pipeline

Runtime 内部有一个 Pipeline，由多个 Step 组成：

```
runtime/
  steps/
    asr_step.py              # 语音转文字
    memory_retrieve_step.py  # 检索相关记忆
    character_step.py        # 加载 Character 状态
    decision_step.py         # Strategy → Planner → Reasoner
    tool_step.py             # 执行工具调用
    memory_save_step.py      # 保存本次交互到记忆
    emotion_step.py          # 更新情绪状态
    tts_step.py              # 文字转语音
    live2d_step.py           # 更新 Live2D 表情/动作
  pipeline.py                # 编排 Step
  runtime.py                 # dispatch(event) → pipeline.run(context)
  context.py                 # Step 间共享上下文（Event + State + Result）
  state_store.py             # 全局状态中心
```

每个 Step 实现：

```python
class Step(ABC):
    @abstractmethod
    async def run(self, ctx: Context) -> None: ...
```

Step 之间通过 `Context` 对象传递数据。新增能力 = 新增 Step + 注册到 Pipeline。Runtime 本身不膨胀。

### 3.4 Event Sources（不是第二个 Runtime）

Scheduler、Watcher、Reminder、Heartbeat 都是 Event Producer。

它们不处理逻辑。它们只生产 Event 并调用 `Runtime.dispatch(event)`。

没有 BackgroundRuntime。没有第二个入口。

### 3.5 State Store

所有模块的状态集中管理：

```
StateStore
  ├── conversation_state     # 当前对话上下文
  ├── character_state        # 当前角色 + 情绪 + 关系
  ├── player_state           # 播放器状态（playing / paused / idle）
  ├── audio_state            # 音频设备状态
  ├── session_state          # 会话元信息
  └── service_state          # 各 Provider 健康状态
```

规则：
- 所有模块只能读写 State Store
- 禁止模块内部缓存状态
- State Store 是唯一真相来源

---

## 四、Domain

Domain 负责业务逻辑。Domain 不知道 Provider。Domain 只引用 Interface。

### Character（核心）

```
Character
  ├── Persona          # 身份设定、性格基底
  ├── Emotion          # 当前情绪（不是独立 Service）
  ├── Mood             # 长期心情趋势
  ├── Relationship     # 与用户的关系状态
  ├── Preference       # 偏好（从记忆学习）
  ├── Goal             # 当前目标
  └── Initiative       # 主动性配置
```

所有交互在 Character 上下文中发生。不是 `LLM.chat()`，而是 `Character.respond(context)`。LLM 只是 Character 的推理引擎。

### Memory

Memory 不是单个 Service。Memory 是五个独立操作：

| 操作 | 调度策略 | 说明 |
|------|---------|------|
| `Store(event)` | 同步 | 记录原始交互 |
| `Retrieve(context)` | 同步（延迟敏感） | 检索相关记忆 |
| `Consolidate()` | 后台 | 合并短期记忆到长期 |
| `Summarize()` | 后台 | 生成摘要 |
| `Forget()` | 定时 | 遗忘策略 |

### Scheduler / Watcher / Reminder

属于 Domain 层的策略模块。它们的行为逻辑（什么条件下触发什么 Event）由 Character 配置驱动。

---

## 五、Interface

Interface 是稳定契约。Interface 属于独立层，不属于 Provider。

```python
class LLMInterface(ABC):
    @abstractmethod
    async def generate(self, messages: list, **kwargs) -> str: ...
    @abstractmethod
    async def generate_stream(self, messages: list, **kwargs) -> AsyncIterator[str]: ...

class TTSInterface(ABC):
    @abstractmethod
    async def synthesize(self, text: str, voice: str) -> bytes: ...

class ASRInterface(ABC):
    @abstractmethod
    async def transcribe(self, audio: bytes, lang: str) -> str: ...

class MemoryInterface(ABC):
    @abstractmethod
    async def store(self, event: Event) -> None: ...
    @abstractmethod
    async def retrieve(self, context: Context) -> list[MemoryItem]: ...

class Live2DInterface(ABC):
    @abstractmethod
    async def set_expression(self, emotion: str) -> None: ...
    @abstractmethod
    async def set_gesture(self, gesture: str) -> None: ...
```

每个 Interface 必须带 Mock：

```python
class MockLLM(LLMInterface):
    """返回固定回复，用于测试。"""
    async def generate(self, messages, **kwargs) -> str:
        return '{"thought": "test", "segments": [], "final_reply": "Hello!"}'
```

以及 Replay：

```python
class ReplayLLM(LLMInterface):
    """回放真实请求记录，用于 bug 重现。"""
    def __init__(self, fixture_path: str): ...
```

---

## 六、Provider

### 6.1 结构

Provider 实现 Interface。

```
providers/
  llm/
    __init__.py       # 注册
    deepseek.py       # class DeepSeekLLM(LLMInterface)
    claude.py         # class ClaudeLLM(LLMInterface)
    openai.py
    mock.py           # class MockLLM(LLMInterface)
    replay.py         # class ReplayLLM(LLMInterface)
  tts/
    __init__.py
    gsvi.py
    edge.py
    qwen.py
    mock.py
  asr/
    __init__.py
    sensevoice.py
    whisper.py
    mock.py
  live2d/
    __init__.py
    open_llm_vtuber_adapter.py  # Live2DInterface 实现，包裹 Open-LLM-VTuber
```

### 6.2 ProviderRegistry + Factory

```python
class ProviderRegistry:
    """发现和管理所有 Provider。"""
    def register(self, interface: type, name: str, provider: type) -> None: ...
    def resolve(self, interface: type, name: str) -> type: ...

class ProviderFactory:
    """创建 Provider 实例。"""
    def create(self, interface: type, name: str, **config) -> Interface: ...
```

Factory 解决创建，Registry 解决发现。未来插件可以 `registry.register(LLMInterface, "my-llm", MyLLM)`。

### 6.3 Adapter

Adapter 是 Provider 的一种实现方式——用于包裹第三方项目。

Adapter 属于 Provider 层，不是独立一层。

```
providers/live2d/
  open_llm_vtuber_adapter.py    # 实现 Live2DInterface
  open_llm_vtuber_adapter/      # 如果 adapter 需要多个辅助文件
```

---

## 七、Integration

Integration 目录统一存放所有外部项目和第三方系统。

```
integrations/
  open_llm_vtuber/       # 第三方项目本身，不修改
  open_hanako/           # 参考项目
  gpt_sovits/            # 第三方模型
  obs/                   # 未来集成
  discord/               # 未来集成
```

Integration 目录中的代码：Runtime 知道它存在，但只通过 Provider/Adapter 调用。

整个目录可以理解为"外部世界"。Runtime 根本没有 `import integrations`。

---

## 八、Legacy

```
legacy/
  bridge/          # 旧 bridge/server.py，迁移完成后删除
  mcp/             # 旧 app/mcp/，迁移完成后删除
  modules/memory/  # 旧 JSONL memory，迁移完成后删除
```

Legacy 规则：
- 可以调用，禁止新增
- 每次提交必须减少 legacy 行数
- 当 legacy/ 为空时，删除这个目录

---

## 九、目录结构完整版

```
app/
  runtime/
    runtime.py              # dispatch(event)
    pipeline.py             # 编排 Steps
    context.py              # Step 间上下文
    steps/
      asr_step.py
      memory_retrieve_step.py
      character_step.py
      decision_step.py
      tool_step.py
      memory_save_step.py
      emotion_step.py
      tts_step.py
      live2d_step.py
    state_store.py          # 全局状态中心

  domain/
    character/
      character.py          # Character 聚合
      persona.py
      emotion.py
      relationship.py
      initiative.py
    conversation/
      conversation.py
    memory/
      store.py              # Store(event)
      retrieve.py           # Retrieve(context)
      consolidate.py        # Consolidate()
      summarize.py          # Summarize()
      forget.py             # Forget()
    scheduler/
      scheduler.py
    vision/
      vision.py

  interfaces/
    llm.py                  # LLMInterface + MockLLM + ReplayLLM
    tts.py                  # TTSInterface + MockTTS + ReplayTTS
    asr.py                  # ASRInterface + MockASR
    live2d.py               # Live2DInterface + MockLive2D
    memory.py               # MemoryInterface + MockMemory
    tool.py                 # ToolInterface + MockTool
    vision.py               # VisionInterface

  providers/
    llm/
      __init__.py           # register(LLMInterface, "deepseek", DeepSeekLLM)
      deepseek.py
      claude.py
      openai.py
      mock.py
      replay.py
    tts/
      __init__.py
      gsvi.py
      edge.py
      qwen.py
      mock.py
    asr/
      __init__.py
      sensevoice.py
      whisper.py
      mock.py
    live2d/
      __init__.py
      open_llm_vtuber_adapter.py
    registry.py             # ProviderRegistry
    factory.py              # ProviderFactory

  config/
    settings.py

integrations/
  open_llm_vtuber/
  open_hanako/
  gpt_sovits/

legacy/
  bridge/
  mcp/

frontend/
  src/                      # 前端源文件
  dist/                     # 构建产物

run.py                      # 启动入口（渐变为只启动 Runtime）
ARCHITECTURE_v2.md
```

---

## 十、与 Current 的差异

| 维度 | Current | Target |
|------|---------|--------|
| 入口 | 多个（bridge WebSocket、AgentLoop、CLI） | `Runtime.dispatch(event)` 唯一 |
| 状态管理 | 模块级全局变量 ~30 个 | State Store 统一管理 |
| Brain | 系统"中心" | Strategy 组合，可替换可拆解 |
| Character | 无独立模块，散布在 bridge 和 loader | Character 聚合，驱动所有交互 |
| 第三方 | 部分直接 import 部分复制 | 全部通过 Integration + Provider |
| Interface | 不存在（直接 import Provider） | 独立层，每个能力一个 Interface |
| Mock | 无 | 每个 Interface 自带 Mock + Replay |
| 测试 | 0 文件 | Pipeline + MockProvider 可测 |
| Bridge | 1590 行巨块，包揽一切 | 不存在（功能迁入 Runtime） |
| 重复模块 | app/mcp/ vs app/legacy/mcp_old/ | 不存在（Legacy 冻结 + 删除） |

---

## 十一、Migration 策略

### Phase 1: Make Runtime.dispatch() the real production entry

Fill `_setup_pipeline()` with real Step instances. Register at least MockLLM in the provider registry so the pipeline can execute end-to-end for testing.

### Phase 2: Convert bridge into a thin transport layer

Extract WebSocket handler, character loading, system prompt building from bridge/server.py into proper modules. Bridge calls Runtime.dispatch() for each incoming message.

### Phase 3: Route all production traffic through Runtime

Modify run.py to use CompanionRuntime instead of AgentLoop/TurnRuntime. Microservices remain as subprocesses but called through Interfaces.

### Phase 4: Complete missing pipeline steps

Add memory_save_step and emotion_step. Fix DecisionStep planner to build real message lists from context. Fix ToolStep data flow.

### Phase 5: Migrate legacy implementations one module at a time

Wire existing HTTP adapters (OpenAILLMAdapter, HTTPASRAdapter, HTTPTTSAdapter) as Provider implementations. Register them. Move one domain module at a time.

### Phase 6: Remove obsolete code

Delete legacy directories. Clean up duplicate state stores. Remove dead code paths.

---

## 十二、架构决策记录

### ADR-001: Runtime.dispatch(event) 而非多个入口

**状态**: 已采纳

**背景**: 当前系统有 bridge WebSocket、AgentLoop、CLI 三个入口，导致路径分裂。

**决策**: 所有交互统一为 Event，通过 `Runtime.dispatch(event)` 进入。

**后果**: 行为一致、路径可追踪、新增入口不用重复逻辑。

### ADR-002: Character 而非 Brain 作为中心

**状态**: 已采纳

**背景**: 这是一个长期陪伴 AI，不是聊天程序。长期稳定的不是推理能力，而是身份。

**决策**: Character 聚合 Persona、Emotion、Relationship、Preference、Goal。每次交互是 `Character.respond(context)`。

**后果**: Brain 降级为可替换的 Strategy。Character 跨版本稳定。

### ADR-003: Interface 独立层

**状态**: 已采纳

**背景**: Provider 频繁替换。如果 Interface 属于 Provider，替换时需要同时修改 Interface 和 Provider。

**决策**: Interface 属于独立层，不属于 Provider。Provider 实现 Interface。

**后果**: 新增 Provider 不修改 Interface。Interface 自带 Mock 和 Replay。

### ADR-004: State Store 统一状态

**状态**: 已采纳

**背景**: 当前状态分散在模块级全局变量、AppState、bootstrap/state。任意模块可自由缓存状态，导致不一致。

**决策**: 所有模块读写 State Store。禁止模块内部缓存状态。

**后果**: 状态可观测、可恢复、可测试。

---

> 本文档是 Target Architecture。它描述的不是现在的代码，而是未来想变成的样子。
>
> 当前代码在 `C:\Users\LENOVO\Desktop\c++\ai`。里面有 bridge/server.py 的 1590 行，有重复的 mcp 目录，有 0 个测试。这些都知道。它们不会在一夜之间消失。但每一步迁移都应该让 ARCHITECTURE_v2.md 离现实更近一点。
