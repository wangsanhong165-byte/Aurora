# Architecture Freeze Report — Phase 5.6

> **Date**: 2026-06-29
> **Status**: Architecture is frozen effective immediately
> **Scope**: `app/` directory, all Python modules (87 files audited)

---

## Executive Summary

The Companion Runtime architecture has been frozen after 5 phases of migration. All architectural boundaries, layer responsibilities, interfaces, and domain models are documented and stable. Future architecture changes require a documented proposal per the Migration Policy (§9 of the Constitution).

**Key decision**: After Phase 5.6, the default answer to "Should we refactor the architecture?" is **No**.

---

## What Was Frozen

### 1. Layer Architecture (9 layers)

| Layer | Directory | Responsibility |
|-------|-----------|---------------|
| Bridge | `app/bridge/` | Transport adapters (WebSocket → Runtime) |
| Runtime | `app/runtime/` | Single entry point, pipeline orchestration, lifecycle |
| Services | `app/services/` | Background processes feeding events |
| Strategy | `app/core/intent.py` | Pure decision logic (no I/O) |
| Domain | `app/domain/` | Pure data models and business logic |
| Interface | `app/interfaces/` | Abstract contracts (6 interfaces) |
| Provider | `app/providers/` | Protocol translation (Interface → external API) |
| Adapter | `app/models/` | SDK wrappers (zero business logic) |
| Core | `app/core/` | Foundational utilities (StateStore, EventBus) |

### 2. 10 Permanent Architectural Rules

| Rule | Description |
|------|-------------|
| R1 | Runtime is the only execution entry point |
| R2 | Runtime owns lifecycle |
| R3 | Providers translate external protocols |
| R4 | Runtime only consumes domain models |
| R5 | Services never know concrete providers |
| R6 | Adapters never contain business logic |
| R7 | Strategy decides behavior, Runtime executes behavior |
| R8 | Provider replacement requires only registration |
| R9 | Legacy code is read-only |
| R10 | New functionality must integrate through Runtime |

### 3. 6 Stabilized Interfaces

| Interface | Methods | Real Provider(s) |
|-----------|---------|------------------|
| `LLMInterface` | `generate()`, `generate_stream()` | OpenAILLMProvider |
| `TTSInterface` | `synthesize()`, `speak()` | HTTPTTSProvider |
| `ASRInterface` | `transcribe()` | HTTPASRProvider |
| `MemoryInterface` | `start()`, `store()`, `retrieve()`, `consolidate()`, `summarize()`, `forget()`, `shutdown()`, `notify_turn()` | SQLiteMemory |
| `Live2DInterface` | `set_expression()`, `set_gesture()`, `speak()` | BridgeLive2DProvider, OpenLLMVTuberProvider |
| `ToolInterface` | `execute()`, `list_tools()` | LegacyToolProvider |

### 4. 8 Stabilized Domain Models

| Model | Type | File |
|-------|------|------|
| `LLMResponse` | `@dataclass` | `app/interfaces/llm.py` |
| `ToolCall` | `@dataclass` | `app/interfaces/llm.py` |
| `Event` | `@dataclass` | `app/runtime/event.py` |
| `Context` | `@dataclass` | `app/runtime/context.py` |
| `Character` | class (aggregate) | `app/domain/character/character.py` |
| `Conversation` | class | `app/domain/conversation/conversation.py` |
| `EmotionState` | class | `app/domain/character/emotion.py` |
| `StateStore` | class (singleton) | `app/core/state_store.py` |

### 5. Pipeline Contract

**8 steps in fixed order**:

```
ASRStep → CharacterStep → MemoryRetrieveStep → DecisionStep
    → EmotionStep → MemorySaveStep → TTSStep → Live2DStep
```

**Step interface**:
```python
class Step(ABC):
    async def run(self, ctx: Context) -> None:
        # Mutate ctx in place
        # Set ctx.error to short-circuit
```

---

## Compliance Audit Results

| Tier | Count | Key Findings |
|------|-------|-------------|
| **C1 (Critical)** | **0** | No layer violations, no Runtime bypasses, no business logic in providers |
| **C2 (Recommended)** | 5 | Duplicated prompt-building logic (3 copies), emotion detection in Step, duplicate Plan class, missing interface docstrings, missing error mocks |
| **C3 (Acceptable)** | 7 | app/memory as infrastructure layer, state_store re-export, dead ChatPipeline code, brain/ module overlap, tools/ re-export shim, hardcoded CJK strings, fallback provider covers all interfaces |

**Compliance rate (C1-free): 100%**

---

## Architecture Documentation Delivered

| Document | Location | Content |
|----------|----------|---------|
| **ARCHITECTURE_CONSTITUTION.md** | `/ARCHITECTURE_CONSTITUTION.md` | Constitutional rules, layer definitions, interfaces, domain models, pipeline contract, extension points, migration policy, compliance tiers |
| **Compliance Audit** | `docs/architecture/compliance_audit.md` | Full audit of all 87 files, C1/C2/C3 findings with remediation plan |
| **Interface Stabilization** | `docs/architecture/interface_stabilization.md` | All 6 interfaces with method signatures, providers, stability notes |
| **Domain Models** | `docs/architecture/domain_models.md` | All 8 domain models with fields, consumers, stabilization history |
| **Extension Guide** | `docs/architecture/extension_guide.md` | How to add providers, steps, events, services, and tools — with code examples |
| **Provider Guide** | `docs/architecture/provider_guide.md` | Provider registration, discovery, lifecycle, resolution chain, common issues |
| **Migration History** | `docs/architecture/migration_history.md` | Complete history of all 6 migration phases |
| **Architecture Freeze Report** | `docs/architecture/architecture_freeze_report.md` | **This document** — the final report |

---

## Current Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                          Bridge                                   │
│  app/bridge/server.py, app/bridge/runtime_handler.py              │
│  WebSocket ↔ Runtime.dispatch() ← reads ctx.*                     │
├──────────────────────────────────────────────────────────────────┤
│                        Runtime                                     │
│  app/runtime/runtime.py — CompanionRuntime                         │
│    ├─ dispatch(event) → Pipeline.run() → Context                   │
│    ├─ _setup_pipeline() — resolve providers, build steps            │
│    ├─ _init_memory_ticker() / _init_initiative_system()             │
│    │  / _init_screen_watcher()                                     │
│    └─ shutdown()                                                   │
│                                                                     │
│  app/runtime/pipeline.py — Pipeline + Step(ABC)                     │
│  app/runtime/context.py — Context dataclass                         │
│  app/runtime/event.py — Event dataclass + EventType                 │
│  app/runtime/steps/ — 8 Step implementations                         │
│  app/runtime/prompts.py — build_initiative_prompt()                 │
├──────────────────────────────────────────────────────────────────┤
│ ┌────────────┐  ┌──────────┐  ┌────────────┐  ┌───────────────┐  │
│ │ Services   │  │ Domain   │  │ Strategy   │  │ Interface     │  │
│ │ initiative │  │ character│  │ intent.py  │  │ llm, tts, asr │  │
│ │ checker    │  │ convers. │  │ candidates │  │ memory, live2d│  │
│ │ screen     │  │ memory   │  │ decide     │  │ tool          │  │
│ │ watcher    │  │ scheduler│  │            │  │ (6 ABCs)      │  │
│ └────────────┘  └──────────┘  └────────────┘  └───────────────┘  │
├──────────────────────────────────────────────────────────────────┤
│                     Provider (translation layer)                   │
│  app/providers/llm/openai_adapter.py   — OpenAILLMProvider         │
│  app/providers/tts/http_adapter.py     — HTTPTTSProvider           │
│  app/providers/asr/http_adapter.py     — HTTPASRProvider           │
│  app/providers/memory/sqlite_memory.py — SQLiteMemory              │
│  app/providers/tool/legacy_provider.py — LegacyToolProvider        │
│  app/providers/live2d/*.py             — Bridge/OpenLLMVTuber      │
├──────────────────────────────────────────────────────────────────┤
│                     Adapter (SDK wrappers)                          │
│  app/models/http_adapters.py — OpenAILLMAdapter, HTTPTTSAdapter,   │
│                                HTTPASRAdapter                       │
├──────────────────────────────────────────────────────────────────┤
│                     External SDKs                                   │
│  openai, requests, sqlite3, sounddevice, soundfile, httpx, aiohttp │
└──────────────────────────────────────────────────────────────────┘
```

---

## Execution Flow

```
User Input (text/voice)
    │
    ▼
Bridge (WebSocket)
    │
    ▼
CompanionRuntime.dispatch(event)
    │
    ├─ Create Context(event)
    ├─ Set ctx.user_text from event payload
    ├─ Inject Conversation into ctx.state
    ├─ Increment turn_count
    │
    ▼
Pipeline.run(ctx) — 8 sequential steps
    │
    ├─ ASRStep: speech → text (voice only)
    ├─ CharacterStep: inject character + emotion
    ├─ MemoryRetrieveStep: query → memories
    ├─ DecisionStep: Planner → LLM.generate → reply + segments + tool_calls
    ├─ EmotionStep: analyze reply → update emotion
    ├─ MemorySaveStep: persist turn → memory
    ├─ TTSStep: reply_text → audio bytes
    └─ Live2DStep: emotion + audio → expression + playback
    │
    ▼
Bridge reads: ctx.reply_text, ctx.audio, ctx.emotion
    │
    ▼
WebSocket response to client
```

---

## Recommended Next Steps

1. **Consolidate prompt-building logic** (C2-1) — highest-impact remediation, eliminates 3-way duplication
2. **Move emotion detection to domain** (C2-2) — clean separation of concerns
3. **Add interface docstrings** (C2-4) — complete the interface contract documentation
4. **Remove dead ChatPipeline code** (C3-3) — cleanup after architecture freeze
5. **Erase `app/tools/` shim** (C3-5) — migrate consumers to `app/legacy/tools/` directly

---

## Migration Policy (summary)

Architecture changes require a documented proposal when they involve:
- Adding a new layer
- Moving files between layers
- Adding a new dependency direction
- Modifying a stabilized Interface or Domain Model signature
- Changing the Pipeline execution order or Step interface

Proposals must include: rationale, alternatives, impact analysis, migration plan, rollback plan.
