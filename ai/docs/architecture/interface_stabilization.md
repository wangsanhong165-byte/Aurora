# Interface Stabilization Report

> **Status**: Ratified — all 6 interfaces are stable
> **Date**: 2026-06-29
> **Constitution ref**: §4

---

## Overview

Six interfaces define the contract between Runtime (orchestration) and Provider (translation). All are abstract base classes in `app/interfaces/`. Each interface has at least one Mock implementation for testing.

---

## 1. `LLMInterface` — STABLE

**File**: `app/interfaces/llm.py`
**Provider key**: `"llm"`
**Mock**: `MockLLM`, `ReplayLLM`

```python
class LLMInterface(ABC):
    async def generate(self, messages: list[dict], **kwargs) -> LLMResponse: ...
    async def generate_stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]: ...
```

**Canonical return type**: `LLMResponse(reply, segments, tool_calls, messages, error)`

**Stability notes**:
- `generate()` returns a typed `LLMResponse` dataclass — no JSON strings escape
- `generate_stream()` returns `AsyncIterator[str]` (token strings for streaming display)
- `ToolCall` dataclass nested in `LLMResponse`: `name: str`, `args: dict[str, Any]`
- Protocol unification (Phase 5.5) eliminated double-encoded JSON — all normalization is inside providers
- **Provider implementations**: `OpenAILLMProvider` (real), `MockLLM` (test), `ReplayLLM` (record/replay)

---

## 2. `TTSInterface` — STABLE

**File**: `app/interfaces/tts.py`
**Provider key**: `"tts"`
**Mock**: `MockTTS`

```python
class TTSInterface(ABC):
    async def synthesize(self, text: str, voice: str = "", **kwargs) -> bytes: ...
    async def speak(self, text: str, voice: str = "", **kwargs) -> str: ...
```

**Stability notes**:
- `synthesize()` returns raw audio bytes (WAV PCM)
- `speak()` is a convenience that synthesizes and marks as spoken — returns `"spoken"`
- `**kwargs` allows provider-specific parameters (language, ref_audio, speaker) without interface changes
- **Provider implementations**: `HTTPTTSProvider` (real), `MockTTS` (test)

---

## 3. `ASRInterface` — STABLE

**File**: `app/interfaces/asr.py`
**Provider key**: `"asr"`
**Mock**: `MockASR`

```python
class ASRInterface(ABC):
    async def transcribe(self, audio: bytes, language: str = "") -> str: ...
```

**Stability notes**:
- Minimal interface — single method, single responsibility
- `audio` is raw bytes (WAV PCM), `language` is optional BCP-47 tag
- Returns plain text transcription
- **Provider implementations**: `HTTPASRProvider` (real), `MockASR` (test)

---

## 4. `MemoryInterface` — STABLE

**File**: `app/interfaces/memory.py`
**Provider key**: `"memory"`
**Mock**: `MockMemory`

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

**Stability notes**:
- Largest interface — 7 methods covering lifecycle, storage, retrieval, consolidation, and summarization
- `start()`/`shutdown()` are synchronous lifecycle hooks called by Runtime
- `notify_turn()` is a signal-only method — the provider decides what to do with it
- `retrieve()` returns `list[dict]` with a flexible schema (callers check `type` and `data` keys)
- **Provider implementations**: `SQLiteMemory` (real), `MockMemory` (test)
- **Lifecycle**: Only Runtime calls `start()` and `shutdown()` — no other module manages memory lifecycle

---

## 5. `Live2DInterface` — STABLE

**File**: `app/interfaces/live2d.py`
**Provider key**: `"live2d"`
**Mock**: `MockLive2D`

```python
class Live2DInterface(ABC):
    async def set_expression(self, emotion: str) -> None: ...
    async def set_gesture(self, gesture: str) -> None: ...
    async def speak(self, audio: bytes, expression: str) -> None: ...
```

**Stability notes**:
- Three methods covering visual expression, gesture, and audio playback
- `expression` parameter is a string emotion name (from `EmotionState.VALID_EMOTIONS`)
- `audio` is raw WAV bytes (from TTS provider)
- **Provider implementations**: `BridgeLive2DProvider` (default, bridge relay), `OpenLLMVTuberProvider` (alternative, HTTP API), `MockLive2D` (test)
- BridgeLive2DProvider also has `start()`/`shutdown()` lifecycle for audio player thread

---

## 6. `ToolInterface` — STABLE

**File**: `app/interfaces/tool.py`
**Provider key**: `"tool"`
**Mock**: `MockTool`

```python
class ToolInterface(ABC):
    async def execute(self, name: str, args: dict) -> str: ...
    async def list_tools(self) -> list[dict]: ...
```

**Stability notes**:
- The simplest interface — two methods for discovering and executing tools
- `list_tools()` returns OpenAI-compatible tool schemas (`list[dict]` with `name`, `description`, `parameters`)
- `execute()` returns JSON string results (legacy format from ToolRegistry)
- **Provider implementations**: `LegacyToolProvider` (real, wraps ToolRegistry + MCP), `MockTool` (test)
- Tool results are JSON strings because downstream (MCP, builtins) returns JSON strings — this is a legacy constraint

---

## Summary

| Interface | Methods | Real Provider(s) | Mock(s) | Stability |
|-----------|---------|------------------|---------|-----------|
| LLMInterface | 2 | OpenAILLMProvider | MockLLM, ReplayLLM | ✅ Stable |
| TTSInterface | 2 | HTTPTTSProvider | MockTTS | ✅ Stable |
| ASRInterface | 1 | HTTPASRProvider | MockASR | ✅ Stable |
| MemoryInterface | 7 | SQLiteMemory | MockMemory | ✅ Stable |
| Live2DInterface | 3 | BridgeLive2DProvider, OpenLLMVTuberProvider | MockLive2D | ✅ Stable |
| ToolInterface | 2 | LegacyToolProvider | MockTool | ✅ Stable |

All 6 interfaces are stable and suitable for freezing. No signature changes are anticipated.
