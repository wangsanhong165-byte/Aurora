# Migration History

> **Date**: 2026-06-29
> **Purpose**: Track all architectural migrations that led to the current frozen state

---

## Phase 1 — Legacy Removal & Package Restructuring

**Objective**: Remove dead code, restructure packages, establish module boundaries.

**Changes**:
- Removed `app.legacy.runtime.turn` (dead code)
- Created `app/providers/` directory structure (6 provider packages)
- Moved `StateStore` from `app.runtime.state_store` to `app.core.state_store` (circular import fix)
- Created `app/runtime/state_store.py` as backward-compatible re-export
- Moved prompt building from `PromptBuilder` class to standalone functions in `app/runtime/prompts.py`
- Extracted `app/core/state.py` into `MoodTracker` + `InputState` enum + state_store re-export

**Architectural impact**:
- Established Provider layer as the translation boundary
- Broke circular import chain between app.input → app.core.state → app.runtime.runtime → app.core.state
- Created Core layer as foundational utilities

---

## Phase 2 — Provider Registry & ProviderFactory

**Objective**: Decouple Runtime from concrete provider implementations.

**Changes**:
- Created `ProviderRegistry` singleton in `app/providers/registry.py`
- Created `ProviderFactory` with auto-discovery mechanism
- All 6 provider packages register themselves on import
- `CompanionRuntime._get_provider_bindings()` returns (Interface, key) pairs
- `CompanionRuntime._build_pipeline_steps()` resolves providers and injects into Steps

**Architectural impact**:
- Runtime no longer imports provider classes directly
- Provider replacement requires only registration (no Runtime modification)
- New providers are auto-discovered on import

---

## Phase 3 — Pipeline & Step Architecture

**Objective**: Replace monolithic Brain with composable Pipeline.

**Changes**:
- Created `Pipeline` (ordered Step chain) and `Step` (abstract base class)
- Created 8 pipeline steps: ASRStep → CharacterStep → MemoryRetrieveStep → DecisionStep → EmotionStep → MemorySaveStep → TTSStep → Live2DStep
- Created `Context` dataclass as the shared pipeline data carrier
- Created `Event` dataclass as the universal input envelope
- `DecisionStep` replaces the old Brain with composable: Planner → LLM.generate → ResponseParser
- `ToolStep` created but not wired into the default pipeline (tool calling handled inside DecisionStep)

**Architectural impact**:
- Pipeline replaces monolithic Brain with composable, testable Steps
- Each Step owns one concern — no more 500-line decision functions
- Pipeline short-circuits on `ctx.error` (remaining Steps skipped)

---

## Phase 4 — Background Services & Initiative System

**Objective**: Extract background monitoring into independent services.

**Changes**:
- Created `InitiativeChecker` — polls initiative queue, fires `on_initiative` callback
- Created `ScreenWatcher` — monitors foreground window, pushes to initiative queue
- Created `InitiativeQueue` — priority queue for proactive speech events
- Created `InitiativeBuffer` — pending proactive speech tracker with expiry
- Extracted `compute_candidates()`/`decide_action()` into `app/core/intent.py`
- All event sources (screen, timer, scheduler, idle) feed into initiative queue
- Services never call LLM directly — they push events for Runtime to process

**Architectural impact**:
- Services are decoupled from Runtime (callback-based, no direct dispatch)
- Strategy layer (intent.py) is pure logic with no I/O
- Event sources are unified through the initiative queue

---

## Phase 5 — Bridge & Transport Layer

**Objective**: Create thin transport adapters that connect external clients to Runtime.

**Changes**:
- Created `RuntimeWebSocketHandler` — routes WebSocket messages to `Runtime.dispatch()`
- `RuntimeWebSocketHandler` reads `ctx.reply_text`, `ctx.audio`, `ctx.emotion` — never modifies pipeline internals
- `server.py` FastAPI app serves Live2D frontend, WebSocket endpoints, REST APIs
- `/client-ws` and `/runtime-ws` WebSocket endpoints both route through Runtime

**Architectural impact**:
- Bridge is thin transport — zero business logic, zero LLM calls
- Bridge reads pipeline output (Context fields) but never writes

---

## Phase 5.5 — LLM Protocol Unification

**Objective**: Eliminate double-encoded JSON response protocol.

**Changes**:
- Created canonical `LLMResponse` dataclass: `reply`, `segments`, `tool_calls`, `messages`, `error`
- Created `ToolCall` dataclass: `name`, `args`
- Moved ALL JSON parsing into `OpenAILLMProvider._normalize()`
- `DecisionStep` became protocol-agnostic — zero `json.loads`, zero provider detection, zero `parsed.get()`
- `OpenAILLMProvider.generate()` returns `LLMResponse` instead of raw dict
- `MockLLM` returns `LLMResponse(reply="Hello!")` instead of JSON string
- `ReplayLLM` returns `LLMResponse()` instead of `""`

**Architectural impact**:
- Single canonical response format across all providers
- DecisionStep consumes `LLMResponse` fields directly — no parsing branches
- Provider normalization is the only place where format conversion happens
- Backward compatibility preserved inside providers only

---

## Phase 5.6 — Architecture Freeze (current)

**Objective**: Freeze the architecture, document all rules, run compliance audit.

**Changes**:
- Created `ARCHITECTURE_CONSTITUTION.md` with permanent architectural rules
- Defined 9 layers with dependency direction, responsibilities, and rules
- Ran compliance audit — 0 Critical, 5 Recommended, 7 Acceptable findings
- Stabilized all 6 interfaces and domain models
- Documented extension points and migration policy
- Created comprehensive architecture documentation in `docs/architecture/`

**Architectural impact**:
- Architecture is frozen — future changes require documented proposals
- 9-layer architecture with clear boundaries and dependency direction
- 6 stabilized interfaces, 8 stabilized domain models
- After Phase 5.6, architecture changes are exceptional rather than routine
