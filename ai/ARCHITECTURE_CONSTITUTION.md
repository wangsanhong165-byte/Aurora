# Architecture Constitution v1 — Companion Runtime

> **Status**: Ratified — Phase 5.6 Architecture Freeze
> **Scope**: `app/` directory, all Python modules
> **Enforcement**: Mandatory. Architecture changes after this freeze require a documented proposal (see Migration Policy §9).

---

## Table of Contents

1. [Layer Architecture](#1-layer-architecture)
2. [Layer Responsibilities](#2-layer-responsibilities)
3. [Layer Rules](#3-layer-rules)
4. [Stabilized Interfaces](#4-stabilized-interfaces)
5. [Stabilized Domain Models](#5-stabilized-domain-models)
6. [Pipeline Contract](#6-pipeline-contract)
7. [Extension Points](#7-extension-points)
8. [Provider Registration](#8-provider-registration)
9. [Migration Policy](#9-migration-policy)
10. [Compliance Tiers](#10-compliance-tiers)

---

## 1. Layer Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     Bridge (transport)                    │
│           WebSocket, HTTP, file-based bridges             │
│                    depends on → Runtime                   │
├──────────────────────────────────────────────────────────┤
│                    Runtime (orchestration)                 │
│     Pipeline, Steps, Context, Event, state_store          │
│           depends on → Domain, Interface, Services        │
├──────────────────────────────────────────────────────────┤
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Services │  │  Domain  │  │Strategy  │  │Interface │  │
│  │(bg proc) │  │ (models) │  │(decide)  │  │(contract)│  │
│  └─────────┘  └──────────┘  └──────────┘  └──────────┘  │
│           depends on → Interface                          │
├──────────────────────────────────────────────────────────┤
│                   Provider (translation)                   │
│   OpenAI, HTTP-ASR, SQLite-Memory, MCP-Tool, Live2D       │
│           depends on → Interface, Adapter                  │
├──────────────────────────────────────────────────────────┤
│                   Adapter (raw SDK wrapper)                │
│   OpenAILLMAdapter, HTTPTTSAdapter, HTTPASRAdapter         │
│           depends on → nothing (external SDKs)             │
├──────────────────────────────────────────────────────────┤
│                   External SDKs / APIs                     │
│   openai, requests, sqlite3, aiohttp, httpx               │
└──────────────────────────────────────────────────────────┘
```

### Layer dependency direction

**DOWNWARD only.** A layer may depend on any lower layer. A layer must NEVER depend on a higher layer.

| Layer | May depend on |
|-------|--------------|
| Bridge | Runtime, Domain, Interface |
| Runtime | Domain, Interface, Services, Core |
| Services | Interface, Core, Domain |
| Strategy | Interface, Domain |
| Domain | Core (StateStore, config) |
| Interface | nothing (stdlib only) |
| Provider | Interface, Adapter, Domain |
| Adapter | nothing (external SDKs only) |
| Core | nothing (stdlib only) |

### Layer location map

| Layer | Directory | File pattern |
|-------|-----------|-------------|
| Runtime | `app/runtime/` | `runtime.py`, `pipeline.py`, `context.py`, `event.py`, `steps/*.py` |
| Domain | `app/domain/` | `character/*.py`, `conversation/*.py`, `memory/*.py`, `scheduler/*.py` |
| Interface | `app/interfaces/` | `llm.py`, `tts.py`, `asr.py`, `memory.py`, `live2d.py`, `tool.py` |
| Provider | `app/providers/` | `llm/*.py`, `tts/*.py`, `asr/*.py`, `memory/*.py`, `tool/*.py`, `live2d/*.py` |
| Adapter | `app/models/` | `http_adapters.py` |
| Strategy | `app/brain/strategies/` | `prompt_strategy.py`, `reflection_strategy.py` |
| Services | `app/services/` | `initiative_checker.py`, `screen_watcher.py` |
| Bridge | `app/bridge/` | `runtime_handler.py`, `server.py` |
| Core | `app/core/` | `state_store.py`, `event_bus.py`, `events.py`, `config.py`, `intent.py` |
| Memory infra | `app/memory/` | `store.py`, `ticker.py`, `compiler.py`, `extractor.py` |

---

## 2. Layer Responsibilities

### 2.1 Runtime Layer

**Purpose**: Single execution entry point for all events. Owns lifecycle.

- `CompanionRuntime.dispatch(event)` is the **only** entry point for processing user input
- `CompanionRuntime` owns: Pipeline construction, provider resolution, background service lifecycle (initiative, screen watcher, memory ticker)
- `Pipeline` executes ordered Steps; stops on `ctx.error`
- `Context` carries all state through the pipeline (event, state dict, reply_text, segments, emotion, audio)
- `Event` is the universal input envelope — every interaction type is an Event
- `Step` implementations read from and write to Context; each Step owns one concern
- `state_store` is the thread-safe global state singleton (activity, turn_count, runtime_initialized)

### 2.2 Domain Layer

**Purpose**: Pure data models and business logic. No I/O. No async.

- `Character` — aggregate combining Persona, EmotionState, RelationshipTracker, MoodTrend, GoalTracker, PreferenceTracker
- `Conversation` — ordered Turn list with history management
- `EmotionState` — emotion name + intensity + history
- `Persona` — character card accessors (name, setting, tone_words, sprites, TTS refs)
- `Turn` — single message (role, content, timestamp, metadata)

### 2.3 Interface Layer

**Purpose**: Abstract contracts (ABCs) that providers implement. No implementation.

- 6 interfaces: `LLMInterface`, `TTSInterface`, `ASRInterface`, `MemoryInterface`, `Live2DInterface`, `ToolInterface`
- Each interface defines ONLY abstract methods + mock implementations for testing
- Methods use canonical types (`LLMResponse`, `bytes`, `str`, `list[dict]`) — no provider-specific types
- Interfaces are in `app/interfaces/` — never import from `app/providers/`

### 2.4 Provider Layer

**Purpose**: Implement interfaces by translating between Runtime protocol and external APIs.

- Each provider implements exactly one Interface
- Providers normalize external API responses into canonical types (`LLMResponse`, etc.)
- Providers handle sync-to-async bridging via `asyncio.to_thread`
- Providers register themselves in `provider_registry` via `__init__.py` side effects
- A provider NEVER contains business logic — only protocol translation

### 2.5 Adapter Layer

**Purpose**: Thin wrappers around external SDKs. Zero business logic.

- `OpenAILLMAdapter` wraps `openai.OpenAI` client
- `HTTPTTSAdapter` wraps `requests.post` to TTS service
- `HTTPASRAdapter` wraps `requests.post` to ASR service
- Adapters are synchronous (called via `asyncio.to_thread` from providers)
- Adapters return plain dicts (not canonical types)

### 2.6 Strategy Layer

**Purpose**: Pure decision logic. No I/O.

- `compute_candidates()` / `decide_action()` — decide whether/why the agent should proactively speak
- Strategies consume domain state (mood, idle time, activity) and return decisions (candidate type, topic, score)
- Strategies never call the LLM, never perform I/O

### 2.7 Services Layer

**Purpose**: Background processes that feed events into Runtime.

- `InitiativeChecker` — polls `InitiativeQueue`, calls `on_initiative` callback which dispatches through Runtime
- `ScreenWatcher` — monitors foreground window, pushes context changes to `InitiativeQueue`
- Services know about `Runtime` only through callbacks — they never call `dispatch()` directly
- Services never call the LLM directly

### 2.8 Bridge Layer

**Purpose**: Transport adapters that connect external clients to Runtime.

- `RuntimeWebSocketHandler` — routes WebSocket messages to `Runtime.dispatch()`
- `server.py` — FastAPI app serving Live2D frontend, WebSocket endpoints, REST APIs
- Bridge reads `ctx.reply_text`, `ctx.audio`, `ctx.emotion` — never modifies pipeline internals
- Bridge is **thin transport** — no business logic, no LLM calls

### 2.9 Core Layer

**Purpose**: Foundational utilities shared by all layers.

- `StateStore` — thread-safe global key-value store
- `EventBus` — pub/sub with queue for UI polling
- `InitiativeQueue` — priority queue for proactive speech events
- `InitiativeBuffer` — pending proactive speech tracker with expiry
- `config.py` — environment loading
- `mood_tracker` — simple keyword-driven mood (0-100)

---

## 3. Layer Rules

### R1 — Runtime is the only execution entry point

All user interaction goes through `CompanionRuntime.dispatch()`. No module bypasses Runtime to call a provider directly for user-facing features.

### R2 — Runtime owns lifecycle

Only `CompanionRuntime` calls `start()` / `shutdown()` on providers and background services. No other module manages provider lifecycle.

### R3 — Providers translate external protocols

A provider's sole job is to convert between external API formats and canonical internal types. Providers never contain:
- Business logic (intent decisions, emotion analysis, conversation management)
- Pipeline orchestration (step ordering, error handling across steps)
- State management (turn counting, activity tracking)

### R4 — Runtime only consumes domain models

Runtime operates on `Context`, `Event`, `LLMResponse`, `Character`, `Conversation`, `EmotionState`. It never accesses provider internals (`_adapter`, raw API responses).

### R5 — Services never know concrete providers

Services interact with providers exclusively through interfaces and callbacks. `InitiativeChecker` calls `self.on_initiative(events)` — it has no reference to `CompanionRuntime` or any provider.

### R6 — Adapters never contain business logic

Adapters wrap SDK calls and return plain dicts. No decisions, no transformations beyond type coercion.

### R7 — Strategy decides behavior, Runtime executes behavior

`compute_candidates()`/`decide_action()` return decisions. Runtime dispatches those decisions through the pipeline. Strategy never performs I/O. Runtime never makes intent decisions.

### R8 — Provider replacement requires only registration

Swapping an implementation requires: (1) implement the Interface, (2) register in `app/providers/<name>/__init__.py`, (3) update config if needed. No Runtime modification required.

### R9 — Legacy code is read-only

Files in `app/legacy/`, `app/brain/`, `app/legacy/tools/` are frozen. No new functionality in legacy modules. New code must integrate through Runtime or Interface.

### R10 — New functionality must integrate through Runtime

New features enter through:
1. New `EventType` constant
2. New `Step` (or existing step enhancement)
3. Handle in `CompanionRuntime.dispatch()` if needed
4. Bridge transports the result to clients

---

## 4. Stabilized Interfaces

### 4.1 `LLMInterface` (`app/interfaces/llm.py`)

```python
class LLMInterface(ABC):
    async def generate(self, messages: list[dict], **kwargs) -> LLMResponse: ...
    async def generate_stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]: ...
```

**Canonical return type**: `LLMResponse(reply, segments, tool_calls, messages, error)`
**Mock**: `MockLLM`, `ReplayLLM`

### 4.2 `TTSInterface` (`app/interfaces/tts.py`)

```python
class TTSInterface(ABC):
    async def synthesize(self, text: str, voice: str = "", **kwargs) -> bytes: ...
    async def speak(self, text: str, voice: str = "", **kwargs) -> str: ...
```

### 4.3 `ASRInterface` (`app/interfaces/asr.py`)

```python
class ASRInterface(ABC):
    async def transcribe(self, audio: bytes, language: str = "") -> str: ...
```

### 4.4 `MemoryInterface` (`app/interfaces/memory.py`)

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

### 4.5 `Live2DInterface` (`app/interfaces/live2d.py`)

```python
class Live2DInterface(ABC):
    async def set_expression(self, emotion: str) -> None: ...
    async def set_gesture(self, gesture: str) -> None: ...
    async def speak(self, audio: bytes, expression: str) -> None: ...
```

### 4.6 `ToolInterface` (`app/interfaces/tool.py`)

```python
class ToolInterface(ABC):
    async def execute(self, name: str, args: dict) -> str: ...
    async def list_tools(self) -> list[dict]: ...
```

---

## 5. Stabilized Domain Models

### 5.1 `LLMResponse` (`app/interfaces/llm.py`)

| Field | Type | Description |
|-------|------|-------------|
| `reply` | `str` | Plain text reply (extracted `final_reply` or `content`) |
| `segments` | `list[dict]` | Per-sentence dicts with `text`, `tone`, `gesture` |
| `tool_calls` | `list[ToolCall]` | Tool invocations requested by the LLM |
| `messages` | `list[dict]` | Full conversation history (for tool-calling loop) |
| `error` | `str` | Provider-level error (empty on success) |

### 5.2 `ToolCall` (`app/interfaces/llm.py`)

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Tool name |
| `args` | `dict[str, Any]` | Tool arguments |

### 5.3 `Event` (`app/runtime/event.py`)

| Field | Type | Description |
|-------|------|-------------|
| `type` | `str` | Event type constant |
| `payload` | `dict` | Event data |
| `source` | `str` | Origin module name |
| `timestamp` | `float` | Creation time |
| `id` | `str` | UUID |

### 5.4 `Context` (`app/runtime/context.py`)

| Field | Type | Description |
|-------|------|-------------|
| `event` | `Event` | The triggering event |
| `state` | `dict` | Shared pipeline state |
| `user_text` | `str` | Transcribed/received user text |
| `reply_text` | `str` | LLM-generated reply (plain text) |
| `segments` | `list` | Per-sentence segments with emotion/gesture |
| `emotion` | `str` | Current emotion name |
| `emotion_intensity` | `float` | 0.0–1.0 |
| `audio` | `bytes` | Synthesized TTS audio |
| `error` | `str` | Pipeline error (empty on success) |

### 5.5 `Character` (`app/domain/character/character.py`)

| Field/Method | Description |
|-------------|-------------|
| `id` | Character ID from card |
| `persona` | `Persona` with name, setting, tone_words, sprites, TTS refs |
| `emotion` | `EmotionState` |
| `relationship` | `RelationshipTracker` |
| `mood` | `MoodTrend` |
| `goals` | `GoalTracker` |
| `preferences` | `PreferenceTracker` |
| `raw_card` | Original card dict (backward compat) |

### 5.6 `Conversation` (`app/domain/conversation/conversation.py`)

| Field/Method | Description |
|-------------|-------------|
| `add_turn(role, content)` | Append a turn |
| `get_history(limit)` | Return message dicts for LLM |
| `turn_count` | Total turns |
| `last_turn` | Most recent Turn or None |

### 5.7 `EmotionState` (`app/domain/character/emotion.py`)

| Field/Method | Description |
|-------------|-------------|
| `VALID_EMOTIONS` | 10 emotions: neutral, happy, sad, angry, surprised, worried, shy, gentle, serious, jealous |
| `set(emotion, intensity)` | Change emotion with history |
| `current` | Current emotion name |
| `intensity` | 0.0–1.0 |

---

## 6. Pipeline Contract

### 6.1 Step interface

```python
class Step(ABC):
    async def run(self, ctx: Context) -> None: ...
```

- Steps mutate `ctx` in place
- Setting `ctx.error` short-circuits the pipeline (remaining steps are skipped)
- Steps must not raise exceptions (catch and set `ctx.error` instead)

### 6.2 Pipeline execution order (8 steps)

```
ASRStep → CharacterStep → MemoryRetrieveStep → DecisionStep
    → EmotionStep → MemorySaveStep → TTSStep → Live2DStep
```

### 6.3 Data flow contract

| Step | Reads | Writes |
|------|-------|--------|
| ASRStep | `ctx.event.type`, `ctx.event.payload.audio` | `ctx.user_text` |
| CharacterStep | `self.character` | `ctx.state["character"]`, `ctx.state["emotion"]` |
| MemoryRetrieveStep | `ctx.user_text` | `ctx.state["memories"]` |
| DecisionStep | `ctx.state["character"]`, `ctx.state["memories"]`, `ctx.state["conversation"]`, `ctx.user_text` | `ctx.reply_text`, `ctx.segments`, `ctx.emotion`, `ctx.state["tool_calls"]`, `ctx.state["tool_results"]` + conversation turns |
| EmotionStep | `ctx.segments`, `ctx.emotion`, `ctx.reply_text` | `character.emotion`, `ctx.emotion`, `ctx.emotion_intensity` |
| MemorySaveStep | `ctx.user_text`, `ctx.reply_text`, `ctx.emotion` | memory store (via provider) |
| TTSStep | `ctx.reply_text`, `ctx.state["character"]` | `ctx.audio` |
| Live2DStep | `ctx.emotion`, `ctx.audio` | Live2D expression + audio playback |

---

## 7. Extension Points

### 7.1 Add a new LLM provider

1. Create `app/providers/llm/my_provider.py`
2. Implement `LLMInterface.generate()` and `generate_stream()`
3. Normalize output into `LLMResponse` (canonical type)
4. Register in `app/providers/llm/__init__.py`:
   ```python
   provider_registry.register(LLMInterface, "my_provider", MyProvider)
   ```
5. Set env config to activate: `LLM_PROVIDER=my_provider`

### 7.2 Add a new TTS/ASR/Live2D/Tool/Memory provider

Same pattern as LLM: implement the Interface, register in the provider's `__init__.py`, configure via env or config file.

### 7.3 Add a new pipeline step

1. Create `app/runtime/steps/my_step.py`
2. Implement `Step.run(ctx: Context)`
3. Add step to `_build_pipeline_steps()` in `runtime.py`
4. Export from `app/runtime/steps/__init__.py`

### 7.4 Add a new event type

1. Add constant to `EventType` in `app/runtime/event.py`
2. Handle the new type in `CompanionRuntime.dispatch()` if special routing is needed
3. Add a Step that reacts to the new event type

### 7.5 Add a new tool (built-in)

1. Create function in `app/tools/builtins/` or `app/legacy/tools/builtins/`
2. Register with `ToolRegistry` via the existing `_register_all` pattern

### 7.6 Add a new background service

1. Create service in `app/services/`
2. Add `_init_my_service()` method in `CompanionRuntime`
3. Wire into `_setup_pipeline()` or a dedicated lifecycle hook
4. Add `shutdown()` cleanup

---

## 8. Provider Registration

### 8.1 Registry pattern

```python
# app/providers/registry.py
provider_registry = ProviderRegistry()  # singleton
provider_registry.register(LLMInterface, "default", OpenAILLMProvider)
provider = provider_registry.resolve(LLMInterface, "default")  # → OpenAILLMProvider
```

### 8.2 Discovery mechanism

`ProviderFactory.discover()` imports all known provider packages. Each package's `__init__.py` registers implementations as a side effect of import. Runtime calls `ProviderFactory.create(InterfaceType)` which triggers discovery once.

### 8.3 Registration points

| Interface | Provider package | Registered names |
|-----------|-----------------|-----------------|
| LLMInterface | `app/providers/llm/` | `openai`, `mock`, `replay`, `default` |
| TTSInterface | `app/providers/tts/` | `default` (HTTPTTSProvider) |
| ASRInterface | `app/providers/asr/` | `default` (HTTPASRProvider) |
| MemoryInterface | `app/providers/memory/` | `default` (SQLiteMemory) |
| ToolInterface | `app/providers/tool/` | `default` (LegacyToolProvider) |
| Live2DInterface | `app/providers/live2d/` | `default` (BridgeLive2DProvider) |

---

## 9. Migration Policy

### 9.1 When is an architecture change allowed?

Architecture changes require a documented proposal in the following cases:
- Adding a new layer
- Moving files between layers (renames are file-moves)
- Adding a new dependency direction (e.g., Domain importing from Provider)
- Modifying a stabilized Interface signature
- Modifying a stabilized Domain Model dataclass
- Changing the Pipeline execution order or Step interface
- Adding a new module outside `app/` that imports from `app/`

### 9.2 When is an architecture change NOT required?

- Adding a new provider (follows established pattern)
- Adding a new pipeline step (follows established pattern)
- Adding a new event type (follows established pattern)
- Adding new methods to non-stabilized modules
- Bug fixes within an existing module
- Adding tests

### 9.3 Proposal requirements

1. **Rationale**: Why the existing architecture cannot accommodate the change
2. **Alternatives considered**: At least 2 alternatives, with reasons for rejection
3. **Impact analysis**: Which layers, interfaces, and modules are affected
4. **Migration plan**: Step-by-step transition, backward compatibility strategy
5. **Rollback plan**: How to revert if the change causes regressions

### 9.4 Approval

Architecture changes require review by at least one other maintainer. The proposal must be documented in `docs/architecture/proposals/` before implementation begins.

---

## 10. Compliance Tiers

Violations identified during architecture audit are classified as:

| Tier | Label | Definition | Action required |
|------|-------|------------|----------------|
| C1 | **Critical** | Layer violation (higher layer depends on lower in wrong direction, bypassing Runtime, business logic in provider) | Must fix before next release |
| C2 | **Recommended** | Pattern violation (interface method missing docstring, missing mock, inconsistent error handling) | Fix within 2 sprints |
| C3 | **Acceptable** | Minor inconsistency (import style, naming convention, commented code) | Fix opportunistically |
