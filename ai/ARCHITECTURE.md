# Architecture — Companion Runtime (Current Code)

> **Date**: 2026-07-14
> **Branch**: 2.2
> **Purpose**: Single authoritative description of the **current** codebase. This document describes what exists NOW, not what the architecture should become.
>
> **Key principle**: Documentation follows Code. If there is a conflict between this document and the code, the code is correct.

---

## 1. System Overview

The system is a **local AI voice companion** (Monika) that runs entirely on Windows. It uses a Pipeline architecture where all user interactions (voice, text, proactive) flow through a single `CompanionRuntime.dispatch()` entry point, pass through an ordered chain of processing Steps, and output audio + Live2D expression to a frontend.

```
Frontend (Electron + React + Live2D)
    │
    ▼
Bridge (FastAPI, port 9528) ─── WebSocket ─── Runtime.dispatch(event)
    │                                                   │
    │  (static files, REST APIs, Live2D model files)    ▼
    │                                               Pipeline (8 Steps)
    │                                                   │
    └───────────────────────────────── Provider ────────┘
```

**Tech stack**:
- **Backend**: Python, FastAPI microservices (ASR :9101, LLM :9102, TTS :9103, Memory :9104, GSVI :9105)
- **Frontend**: Electron + React + Vite + TypeScript (custom component library, no Chakra UI)
- **LLM**: DeepSeek-v4-flash (primary), via OpenAI-compatible API
- **ASR**: Qwen3-ASR (subprocess, port 9101)
- **TTS**: GPT-SoVITS v2Pro (subprocess, port 9105, proxied through :9103)
- **Live2D**: Cubism SDK 5, bridged via WebSocket
- **Memory**: SQLite + FTS5

---

## 2. Runtime (`app/runtime/`)

### 2.1 CompanionRuntime

The **only** entry point for all interaction. Defined in `runtime.py`.

```python
class CompanionRuntime:
    async def dispatch(self, event: Event) -> Context:
        # 1. Create Context from Event
        # 2. Inject Conversation into context state
        # 3. Increment turn counter
        # 4. Run pipeline
        # 5. Notify memory provider (background ticker)
        # 6. Return Context
```

**Singleton**: `runtime = CompanionRuntime()` at module level.

**Dispatch handles these event types**:
| Event type | Source | Payload |
|-----------|--------|---------|
| `speech_received` | VAD/microphone | `{"text": "..."}` |
| `text_received` | Keyboard/API | `{"text": "..."}` |
| `initiative_triggered` | InitiativeChecker | `{"text": "..."}` (generated prompt) |

Note: `vision_updated`, `tool_finished`, `session_resumed` are defined in `EventType` but have no dispatch routing in current code.

### 2.2 Provider Bindings

Runtime resolves 6 providers via `ProviderFactory.create()`:

```python
def _get_provider_bindings(self):
    return [
        (LLMInterface, "llm"),
        (MemoryInterface, "memory"),
        (ToolInterface, "tool"),
        (TTSInterface, "tts"),
        (ASRInterface, "asr"),
        (Live2DInterface, "live2d"),
    ]
```

Each interface is resolved to one provider class. If resolution fails, a fallback no-op provider is used.

### 2.3 Background Services

Started in `_setup_pipeline()`:

| Service | Purpose | Interval |
|---------|---------|----------|
| Memory ticker | Background consolidation/summarization | Managed by Memory provider |
| InitiativeChecker | Proactive speech (120s cooldown, 0.30 threshold) | 15s check cycle |
| ScreenWatcher | Active window monitoring → activity inference | 5s poll |

### 2.4 Shutdown

`shutdown()` stops: memory provider ticker, initiative checker, screen watcher, initiative buffer expiry.

---

## 3. Pipeline (`app/runtime/pipeline.py`)

### 3.1 Step ABC

```python
class Step(ABC):
    @abstractmethod
    async def run(self, ctx: Context) -> None:
        ...
```

Steps mutate `Context` in place. Setting `ctx.error` short-circuits the remaining pipeline.

### 3.2 Pipeline

```python
class Pipeline:
    def add(self, step: Step) -> "Pipeline": ...
    async def run(self, ctx: Context) -> Context:
        for step in self._steps:
            await step.run(ctx)
            if ctx.error:
                break
        return ctx
```

### 3.3 Actual Step Order

From `CompanionRuntime._build_pipeline_steps()`:

```
Step 1: ASRStep              (speech → text; skipped if text already provided)
Step 2: CharacterStep         (inject character persona + emotion into context)
Step 3: MemoryRetrieveStep    (query similar memories for LLM context)
Step 4: DecisionStep          (LLM generate + tool-calling loop, max 5 rounds)
Step 5: EmotionStep           (keyword-based emotion analysis fallback)
Step 6: MemorySaveStep        (persist turn to memory store)
Step 7: TTSStep               (text → audio bytes)
Step 8: Live2DStep            (expression relay + audio playback)
```

**Note**: `ToolStep` exists in `steps/tool_step.py` but is NOT registered in the pipeline. Tool execution happens inside `DecisionStep`'s tool-calling loop instead.

### 3.4 Context

Data carrier between steps. Defined in `context.py`:

```python
@dataclass
class Context:
    event: Event
    state: dict                     # Step-specific data (character, memories, tool_calls, conversation)
    user_text: str                  # Input text from user/event
    reply_text: str                 # LLM-generated reply
    segments: list                  # Per-sentence segment dicts (text, tone, gesture)
    emotion: str                    # Current emotion name
    emotion_intensity: float        # 0.0-1.0
    audio: bytes                    # TTS audio output
    error: str                      # Error message (empty = success)
    status_message: str             # Human-readable progress message
    status_callback: Any            # Optional async callback for status updates
```

---

## 4. Event System (`app/runtime/event.py`)

```python
@dataclass
class Event:
    type: str       # EventType constant
    payload: dict   # Event-specific data
    source: str     # Producer identifier
    timestamp: float
    id: str

class EventType:
    SPEECH_RECEIVED = "speech_received"
    TEXT_RECEIVED = "text_received"
    INITIATIVE_TRIGGERED = "initiative_triggered"
    VISION_UPDATED = "vision_updated"
    TOOL_FINISHED = "tool_finished"
    SESSION_RESUMED = "session_resumed"
```

Note: `VISION_UPDATED`, `TOOL_FINISHED`, and `SESSION_RESUMED` are defined but no code handles them yet.

---

## 5. Interfaces (`app/interfaces/`)

6 abstract base classes. Each defines a contract between Runtime (orchestrator) and Provider (implementation).

### 5.1 LLMInterface (`llm.py`)

```python
class LLMInterface(ABC):
    async def generate(self, messages: list[dict], **kwargs) -> LLMResponse: ...
    async def generate_stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]: ...
```

Return type:
```python
@dataclass
class LLMResponse:
    reply: str                     # Extracted plain text reply
    segments: list[dict]           # Per-sentence segments (text, tone, gesture)
    tool_calls: list[ToolCall]     # Tool invocations requested
    messages: list[dict]           # Full conversation history
    error: str                     # Error string (empty on success)

@dataclass
class ToolCall:
    name: str
    args: dict
```

Mocks: `MockLLM`, `ReplayLLM`

### 5.2 TTSInterface (`tts.py`)

```python
class TTSInterface(ABC):
    async def synthesize(self, text: str, voice: str = "", **kwargs) -> bytes: ...
    async def speak(self, text: str, voice: str = "", **kwargs) -> str: ...
```

Mock: `MockTTS`

### 5.3 ASRInterface (`asr.py`)

```python
class ASRInterface(ABC):
    async def transcribe(self, audio: bytes, language: str = "") -> str: ...
```

Mock: `MockASR`

### 5.4 MemoryInterface (`memory.py`)

```python
class MemoryInterface(ABC):
    def start(self, character_registry=None, llm_provider=None) -> None: ...
    async def store(self, event_type: str, data: dict) -> None: ...
    async def retrieve(self, query: str, limit: int = 10) -> list[dict]: ...
    async def consolidate(self) -> None: ...
    async def summarize(self, since: str) -> str: ...
    async def forget(self, before: str) -> int: ...
    def shutdown(self) -> None: ...
    def notify_turn(self) -> None: ...
```

Mock: `MockMemory`

### 5.5 Live2DInterface (`live2d.py`)

```python
class Live2DInterface(ABC):
    async def set_expression(self, emotion: str, intensity: float = 0.5) -> None: ...
    async def set_gesture(self, gesture: str) -> None: ...
    async def speak(self, audio: bytes, expression: str) -> None: ...
```

Mock: `MockLive2D`

### 5.6 ToolInterface (`tool.py`)

```python
class ToolInterface(ABC):
    async def execute(self, name: str, args: dict) -> str: ...
    async def list_tools(self) -> list[dict]: ...
```

Mock: `MockTool`

---

## 6. Providers (`app/providers/`)

### 6.1 Discovery + Resolution

```python
# ProviderFactory.discover() — called once, imports all 6 provider packages
_PROVIDER_PACKAGES = [
    "app.providers.llm",
    "app.providers.tts",
    "app.providers.asr",
    "app.providers.memory",
    "app.providers.tool",
    "app.providers.live2d",
]
```

Each package's `__init__.py` registers implementations as a side effect of import.

Resolution chain: `resolve(Interface, name)` → `resolve(Interface, "default")` → `None`

### 6.2 Actual Provider Implementations

| Interface | Provider Class | File | Registration Condition |
|-----------|---------------|------|----------------------|
| LLM | `OpenAILLMProvider` | `providers/llm/openai_adapter.py` | `DEEPSEEK_API_KEY` or `OPENAI_API_KEY` set |
| TTS | `HTTPTTSProvider` | `providers/tts/http_adapter.py` | `TTS_URL` or `TTS_PORT` set |
| ASR | `HTTPASRProvider` | `providers/asr/http_adapter.py` | `ASR_URL` or `ASR_PORT` set |
| Memory | `SQLiteMemory` | `providers/memory/sqlite_memory.py` | Always registered |
| Live2D | `BridgeLive2DProvider` | `providers/live2d/bridge_provider.py` | `config/live2d_models.json` exists |
| Tool | `LegacyToolProvider` | `providers/tool/legacy_provider.py` | `config/mcp_servers.json` exists |

When a registration condition is not met, the default resolves to the Mock implementation.

### 6.3 LLM Provider Detail

`OpenAILLMProvider` communicates with DeepSeek API via OpenAI-compatible endpoint:
- Reads `DEEPSEEK_API_KEY` or `OPENAI_API_KEY` from env
- Uses `openai` Python SDK
- Returns normalized `LLMResponse` (no JSON strings escape provider layer)

### 6.4 Live2D Provider Detail

`BridgeLive2DProvider` relays expression commands to the bridge via HTTP POST:
- `set_expression(emotion, intensity)` → `POST /live2d/expression`
- `set_gesture(gesture)` → `POST /live2d/gesture`
- `speak(audio, expression)` → local audio playback via `AsyncAudioPlayer`

### 6.5 Provider Lifecycle

| Interface | start() | shutdown() | Notes |
|-----------|---------|------------|-------|
| MemoryInterface | ✅ `start(registry, llm)` | ✅ `shutdown()` | Background ticker + compiler |
| Live2DInterface | ✅ `start()` (audio player) | ✅ `shutdown()` | Audio playback thread |
| Others | — | — | Stateless |

---

## 7. Domain Models (`app/domain/`)

### 7.1 Character (`app/domain/character/`)

The identity center of the system. An aggregate combining:

```python
class Character:
    id: str
    persona: Persona         # Name, setting, tone words, sprites, TTS refs
    emotion: EmotionState    # Current emotion + intensity
    relationship: RelationshipTracker  # Affinity tracking
    mood: MoodTrend          # Long-term mood analysis
    goals: GoalTracker       # Active goals
    preferences: PreferenceTracker     # Learned user preferences
```

**EmotionState**: 31+ valid emotions including neutral, happy, sad, angry, surprised, worried, shy, gentle, serious, jealous, and 21 Monika-specific tone words (playful, explaining, smile, cheerful, cold, stern, etc.).

### 7.2 Conversation (`app/domain/conversation/`)

Ordered turns with context window management (default max 50 turns).

```python
class Conversation:
    def add_turn(self, role: str, content: str, **metadata) -> None: ...
    def get_history(self, limit: int | None = None) -> list[dict]: ...
    def clear(self) -> None: ...
```

### 7.3 Core (`app/core/`)

| Module | Purpose |
|--------|---------|
| `state_store.py` | Thread-safe singleton dict (get/set/update/snapshot) |
| `event_bus.py` | Pub/sub for internal events |
| `state.py` | Re-exports state_store + mood_tracker |
| `intent.py` | `compute_candidates()`, `decide_action()` — initiative decision logic |
| `initiative_queue.py` | Priority queue for proactive speech triggers |
| `initiative_buffer.py` | Closure detection for initiative messages |

---

## 8. Bridge (`app/bridge/`)

The bridge is a FastAPI server on port 9528. It does **three distinct jobs**:

### 8.1 Transport (correct role)
- `/client-ws` WebSocket — routes messages to `Runtime.dispatch()` via `RuntimeWebSocketHandler` (163 lines)
- `/runtime-ws` WebSocket — alternate endpoint, same handler
- `/ws` — legacy WebSocket, heartbeat + Live2D relay only

### 8.2 Business logic (should be in Runtime/Domain)
- **Pinned memories**: CRUD at `/api/pinned`
- **History management**: File-based JSON storage at `/api/histories` (load, save, index)
- **Live2D model config**: Loading `config/live2d_models.json`, model selection
- **Character info**: Loading active character card via `Runtime.get_character_info()`

### 8.3 Web server (legacy frontend support)
- **Static files**: Serves `frontend/dist/` at `GET /`
- **Live2D model files**: Serves from `models/live2d-models/`
- **Background images**: Serves from external Open-LLM-VTuber directory

### 8.4 REST Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/live2d/expression` | POST | Relay expression to all WS clients |
| `/live2d/gesture` | POST | Relay gesture to all WS clients |
| `/live2d/accessory` | POST | Toggle accessory |
| `/api/pinned` | GET/PUT | Pinned memories |
| `/api/histories` | GET | List conversation histories |
| `/api/models` | GET | List Live2D models |
| `/api/set-model` | POST | Switch Live2D model |
| `/api/set-mode` | POST | Switch UI mode (window/pet) |

### 8.5 Data Flow

```
Frontend (WS /client-ws)
    → Bridge (RuntimeWebSocketHandler)
    → Runtime.dispatch(event)
    → Pipeline (8 Steps)
    → Context (reply_text, audio, emotion)
    ← Bridge reads ctx.*
    ← WS response to frontend

Live2D path (circular):
    Runtime.Live2DStep
    → BridgeLive2DProvider.set_expression("happy")
    → HTTP POST /live2d/expression (back to bridge)
    → bridge WS broadcast → frontend
```

---

## 9. Directory Structure (Current)

```
app/
  runtime/
    runtime.py              # CompanionRuntime.dispatch()
    pipeline.py             # Pipeline + Step ABC (+ dead ChatPipeline)
    context.py              # Context dataclass
    event.py                # Event dataclass + EventType
    state_store.py          # StateStore re-export
    prompts.py              # Initiative prompt builders
    steps/
      asr_step.py
      character_step.py
      memory_retrieve_step.py
      decision_step.py
      emotion_step.py
      memory_save_step.py
      tts_step.py
      live2d_step.py
      tool_step.py          # EXISTS but NOT registered in pipeline

  interfaces/
    llm.py                  # LLMInterface + MockLLM + ReplayLLM
    tts.py                  # TTSInterface + MockTTS
    asr.py                  # ASRInterface + MockASR
    memory.py               # MemoryInterface + MockMemory
    live2d.py               # Live2DInterface + MockLive2D
    tool.py                 # ToolInterface + MockTool

  providers/
    llm/
      __init__.py           # register(LLMInterface, "openai", OpenAILLMProvider)
      openai_adapter.py
    tts/
      __init__.py
      http_adapter.py
    asr/
      __init__.py
      http_adapter.py
    memory/
      __init__.py
      sqlite_memory.py
    tool/
      __init__.py
      legacy_provider.py
    live2d/
      __init__.py
      bridge_provider.py
      open_llm_vtuber_provider.py
    registry.py             # ProviderRegistry (singleton)
    factory.py              # ProviderFactory.discover() + create()

  domain/
    character/
      character.py          # Character aggregate
      persona.py            # Persona (name, setting, tone_words, etc.)
      emotion.py            # EmotionState (31+ emotions)
      relationship.py       # RelationshipTracker
      mood.py               # MoodTrend
      goal.py               # GoalTracker
      preference.py         # PreferenceTracker
    conversation/
      conversation.py       # Conversation (turns, history, context window)

  bridge/
    server.py               # FastAPI server — 918 lines, 3 roles
    runtime_handler.py      # RuntimeWebSocketHandler — 163 lines

  core/
    state_store.py          # StateStore singleton
    state.py                # Re-exports state_store + mood_tracker
    event_bus.py            # Pub/sub
    intent.py               # compute_candidates(), decide_action()
    initiative_queue.py     # Priority queue
    initiative_buffer.py    # Closure detection

  memory/
    store.py                # SQLite+FTS5 storage
    ticker.py               # Background consolidation timer
    compiler.py             # Memory compilation
    extractor.py            # Fact extraction

  brain/                    # FROZEN — pre-Runtime decision engine
    base.py                 # Legacy Plan class
    registry.py             # StrategyRegistry
    strategies/
      prompt_strategy.py    # Legacy PlanningStrategy subclass
      reflection_strategy.py

  services/
    initiative_checker.py   # Proactive speech monitor
    screen_watcher.py       # Active window monitor

  character/
    registry.py             # CharacterRegistry (card loading)

  models/
    http_adapters.py        # Legacy HTTP adapters (11KB) — mostly superseded

  legacy/
    tools/                  # Frozen legacy tool implementations

  tools/                    # Re-export shim → app/legacy/tools/

frontend/
  src/                      # Electron + React + Vite + custom components
  dist/                     # Build output

config/
  characters/monika/        # Character card, pinned memories
  live2d_models.json        # Expression → emotion mappings
  mcp_servers.json          # MCP tool configuration

models/
  live2d-models/            # Live2D model files
    Design_genius_White/
    youxiaomiao/
    ariu/
    mao_zh-Hans/

run.py                      # Startup entry — launches microservices + Runtime
```

**Notable absences** (compared to earlier Target architecture):
- No `integrations/` directory
- No `legacy/` directory
- No `app/interfaces/vision.py`
- No per-provider files like `deepseek.py`, `claude.py`, `gsvi.py`, `edge.py`, `whisper.py`, etc.

---

## 10. Application Startup (`run.py`)

The main entry point:
1. Parses CLI args (`--text`, `--no-vad`, `--runtime`, `--mode`)
2. Launches microservices as subprocesses: ASR(:9101), LLM(:9102), TTS(:9103), MEMORY(:9104), GSVI(:9105)
3. Waits for services to be ready
4. Starts `CompanionRuntime` via `_runtime_main(args)`
5. Runtime is the default mode (line 348: `return _runtime_main(args)`)

---

## 11. Known Problems (Current State)

These are not criticisms — they are accurate descriptions of the current code's limitations:

1. **Bridge is bloated**: 918 lines across 3 roles (transport, business logic, web server). Only `RuntimeWebSocketHandler` (163 lines) is "thin transport."

2. **No VisionInterface**: Defined in `EventType.VISION_UPDATED` but no `app/interfaces/vision.py` exists and no dispatch routing handles vision events.

3. **ToolStep exists but unused**: `steps/tool_step.py` is defined but not registered in the pipeline. Tool execution is handled inside `DecisionStep`'s tool-calling loop.

4. **Emotion detection in Step**: `_detect_emotion()` and keyword lists are hardcoded in `emotion_step.py` instead of being in the domain layer. (Identified as C2-2 in compliance audit.)

5. **No error-path mocks**: All `Mock*` implementations succeed always. No `FailingLLM`/`FailingTTS` variants exist. (Identified as C2-5.)

6. **Dead code**: `ChatPipeline` (legacy v1) preserved in `pipeline.py`. `app/brain/` is frozen but overlaps with Runtime. (Identified as C3-3, C3-4, C3-8.)

7. **app/memory/ duplicated structure**: `app/memory/` (infrastructure) and `app/providers/memory/` (Interface wrapper) coexist. (Identified as C3-1.)

8. **frontend/src/ is a copied project**: The current frontend was taken from another project and feels "uncomfortable" to work with. It has its own architecture in `frontend/src/CLAUDE.md` with 14 context providers and Chakra UI v3.

9. **No test files**: The project has 0 test files. `MockLLM`, `MockMemory`, etc. exist but are not wired to any test runner.

---

## 12. Compliance with Architecture Rules

The frozen architecture rules (from Phase 5.6) and their current compliance status:

| Rule | Description | Status |
|------|-------------|--------|
| R1 | Runtime is the only execution entry point | ✅ Compliant — all input flows through `dispatch()` |
| R2 | Runtime owns lifecycle | ✅ Compliant — `__init__` + `shutdown()` |
| R3 | Providers translate external protocols | ✅ Compliant — no business logic in providers |
| R4 | Runtime only consumes domain models | ✅ Compliant |
| R5 | Services never know concrete providers | ✅ Compliant — use events, never direct provider calls |
| R6 | Adapters never contain business logic | ✅ Compliant |
| R7 | Strategy decides, Runtime executes | ✅ Compliant — `intent.py` is pure logic |
| R8 | Provider replacement requires only registration | ✅ Compliant — pattern verified across all 6 providers |
| R9 | Legacy code is read-only | ✅ Compliant — `app/brain/`, `app/legacy/` not modified |
| R10 | New functionality integrates through Runtime | ✅ Compliant |

All 10 rules are currently satisfied. The primary architectural debt is the **bridge** (multi-role, not thin transport).
