# Architecture Compliance Audit

> **历史快照：** 本审计记录的是 2026-06-29 的 v1 Phase 5.6 冻结状态，
> 其中 `CompanionRuntime.dispatch()`、旧 Bridge Handler 等结论不再描述当前
> Runtime V3。当前架构请以根目录 [ARCHITECTURE.md](../../ARCHITECTURE.md)
> 和 [V3 迁移报告](../runtime/V3_MIGRATION_REPORT.md) 为准。
>
> **Date**: 2026-06-29
> **Scope**: All `app/` Python modules
> **Constitution version**: v1 (Phase 5.6 Freeze)
> **Tiers**: C1 = Critical, C2 = Recommended, C3 = Acceptable

---

## C1 — Critical Violations

**None found.** No layer violations, no bypasses of Runtime, no business logic in providers.

The architecture freeze catches the system in a clean state on all Critical dimensions:

| Check | Result |
|-------|--------|
| Runtime is the only execution entry point | Pass — all user input flows through `CompanionRuntime.dispatch()` |
| No module bypasses Runtime to call providers directly | Pass — no module imports providers except through Interface |
| Providers don't contain business logic | Pass — LLM/TTS/ASR/Memory/Tool/Live2D providers only translate protocols |
| Adapters don't contain business logic | Pass — OpenAILLMAdapter, HTTPTTSAdapter, HTTPASRAdapter only wrap SDK calls |
| Services don't call the LLM directly | Pass — InitiativeChecker/ScreenWatcher use events, never LLM |
| Bridge is thin transport | Pass — RuntimeWebSocketHandler only calls `runtime.dispatch()` and reads `ctx.*` |
| Strategy doesn't perform I/O | Pass — `compute_candidates()`/`decide_action()` are pure functions |
| Legacy code is read-only | Pass — `app/legacy/` has no new additions |

---

## C2 — Recommended Violations

### C2-1: [RECLASSIFIED → C3] Legacy brain module retains duplicate PromptStrategy implementations

**Removed from C2.** This is not an active Runtime architecture issue. See C3-8 below.

---

### C2-2: Emotion detection logic lives in a Pipeline Step

**File**: `app/runtime/steps/emotion_step.py` (lines 7-49)

**Description**: The `_detect_emotion()` function and keyword lists (`_POSITIVE_WORDS`, `_SAD_WORDS`, etc.) are defined inside the Step module. This is business logic (emotion analysis) embedded in the orchestration layer.

**Recommendation**: Move emotion keyword lists and `_detect_emotion()` to `app/domain/character/emotion.py` or a new `app/domain/analysis/emotion_detector.py`. `EmotionStep` should import and call the domain function.

**Severity**: Medium — logic is small and stable, but violates the principle that Steps orchestrate, not decide.

---

### C2-3: [RECLASSIFIED → C3] Duplicate `Plan` class in brain module

**Removed from C2.** The `Plan` class in `app/brain/base.py` is a legacy artifact within the frozen `brain/` module. The active `Plan` in `decision_step.py` is canonical. This is legacy technical debt, not an active architecture issue. See C3-4.

### C2-4: Missing Interface docstrings

**Files**: `app/interfaces/asr.py`, `app/interfaces/tool.py`

**Description**: `ASRInterface.transcribe()` and `ToolInterface.execute()`/`list_tools()` lack parameter documentation. While the method names are self-explanatory, the interface layer should be fully documented as the contract between Runtime and Providers.

**Recommendation**: Add docstrings with `Args:` and `Returns:` sections to all abstract methods.

**Severity**: Low — methods are simple, but interface layer needs full documentation.

---

### C2-5: Missing Mock implementations for error testing

**Files**: All 6 interface files

**Description**: Each interface defines a `Mock*` implementation that succeeds always. There are no error-path mocks (e.g., `FailingLLM` that returns `LLMResponse(error="timeout")`, `FailingTTS` that returns empty bytes).

**Recommendation**: Add `Failing*` mock variants to each interface module for testing pipeline error handling.

**Severity**: Low — missing but not blocking; error coverage is handled by unit tests.

---

## C3 — Acceptable Observations

### C3-1: `app/memory/` as infrastructure layer

**Files**: `app/memory/store.py`, `app/memory/ticker.py`, `app/memory/compiler.py`, `app/memory/extractor.py`

**Description**: The `app/memory/` directory contains SQLite-backed storage, background compilation, and extraction pipelines. It is not a pure domain module (has I/O) and not a pure provider (has business logic). `SQLiteMemory` in `app/providers/memory/` wraps it as an Interface implementation.

This split is acceptable — it separates infrastructure concerns (SQL queries, file I/O, threading) from the Interface contract. However, it means there are two "memory" layers: `app/memory/` (infrastructure) and `app/providers/memory/` (Interface wrapper).

---

### C3-2: `state_store` re-exported from two locations

**Files**: `app/core/state.py` (line 13), `app/runtime/state_store.py`

**Description**: `state_store` is defined in `app/core/state_store.py`, then re-exported from `app/core/state.py` and `app/runtime/state_store.py`. This was done to break circular import chains.

This is acceptable as long as both re-exports use the canonical singleton from `app.core.state_store`. Verified — they do.

---

### C3-3: Dead code in `app/runtime/pipeline.py`

**File**: `app/runtime/pipeline.py` (lines 17-115)

**Description**: `ChatPipeline` (legacy v1) is preserved as dead code alongside the v2 `Pipeline` and `Step` classes. It is marked as such in the docstring.

Acceptable per R9 (legacy code is read-only). Should be removed in a future cleanup pass.

---

### C3-4: `app/brain/` partially overlaps with Runtime

**Files**: `app/brain/base.py`, `app/brain/registry.py`, `app/brain/strategies/`

**Description**: The `brain/` module was the pre-Runtime decision engine. Parts of it (`PlannerStrategy`, `StrategyRegistry`) duplicate functionality now provided by `DefaultPlanner` and the Runtime pipeline. These files are frozen per R9.

---

### C3-5: `app/tools/` is a legacy re-export shim

**File**: `app/tools/registry.py`, `app/tools/builtins/`

**Description**: The entire `app/tools/` module re-exports from `app/legacy/tools/`. This is a compatibility shim. Acceptable as transitional — should be removed when all consumers migrate to `app/legacy/tools/` directly.

---

### C3-6: Hardcoded CJK strings in prompts

**Files**: `app/runtime/prompts.py`, `app/memory/prompts.py`

**Description**: Initiative prompts, output format instructions, and memory compilation prompts contain hardcoded Chinese/Japanese strings. These are tied to the character persona and are not expected to change, but make the code less language-agnostic.

---

### C3-7: `CompanionRuntime._fallback_provider` covers all interfaces

**File**: `app/runtime/runtime.py` (lines 319-339)

**Description**: The static `_fallback_provider()` generates a single class with methods for all 6 interfaces. This works because the methods are never called when a real provider is available, but creates a maintenance burden if new Interface methods are added.

---

### C3-8: Legacy brain module retains duplicate PromptStrategy implementations

**Files**: `app/brain/strategies/prompt_strategy.py`, `app/brain/strategies/reflection_strategy.py`, `app/brain/base.py`

**Description**: The `brain/` module (pre-Runtime decision engine, frozen per R9) retains two `PlanningStrategy` subclasses (`PromptStrategy`, `ReflectionStrategy`) and a `Plan` class that structurally duplicate the `DefaultPlanner` and `Plan` in `app/runtime/steps/decision_step.py`. These are **legacy artifacts** — they are not wired into the Runtime pipeline, not used by any consumer, and do not evolve. Runtime uses only `DefaultPlanner`.

This is classified as **Legacy Technical Debt** rather than an active architectural issue. Resolution depends on a future formal retirement of the `brain/` module. No immediate action needed.

**Classification update history**:
- Previously C2-1 (three-way duplicate prompt builders) — reclassified to C3-8
- Previously C2-3 (duplicate Plan class) — reclassified into C3-8

---

## Compliance Score

| Metric | Value |
|--------|-------|
| C1 (Critical) violations | 0 |
| C2 (Recommended) violations | 3 |
| C3 (Acceptable) observations | 9 |
| Files audited | 87 |
| Compliance rate (C1-free) | 100% |

---

## Recommended Remediation Plan

1. **Short-term** (next 2 sprints): Move emotion detection to domain (C2-2).
2. **Ongoing**: Add interface docstrings (C2-4), add error mocks (C2-5), remove dead code (C3-3).
3. **Future**: When the `brain/` module is formally retired, clean up `PromptStrategy`, `ReflectionStrategy`, and the legacy `Plan` class (C3-8).
