# Phase 0 — Execution Flow Analysis

## Production Paths

There are three production entry points, all using legacy code:

### Path A: Bridge WebSocket (`/client-ws`)

```
Frontend (Open-LLM-VTuber)
  │
  └── WebSocket → app/bridge/server.py: websocket_endpoint()
        │
        ├── text-input → _handle_text_input()
        │     ├── _load_recent_exchanges()    (restore from memory API)
        │     ├── _get_compiled_memory()      (read compiled/memory.md)
        │     ├── _call_llm() ──┬── _call_llm_with_mcp()  (6-round tool loop)
        │     │                 └── _call_llm_structured() (sync OpenAILLMAdapter)
        │     ├── _process_segments()         (TTS + Live2D per segment)
        │     │     ├── _call_tts()           (sync HTTPTTSAdapter)
        │     │     └── _send_audio()         (WebSocket binary)
        │     └── _save_reply() ──┬── _save_to_memory_api()  (POST /memory)
        │                         └── _save_to_current_history() (JSONL)
        │                         └── _trigger_compile() (background)
        │
        ├── mic-audio-end → _handle_voice_input()
        │     ├── _call_asr()                 (sync HTTPASRAdapter)
        │     ├── _get_compiled_memory()
        │     ├── _call_llm()                 (same as text)
        │     ├── _process_segments()         (same as text)
        │     └── _save_reply()               (same as text)
        │
        ├── ai-speak-signal → _call_llm_proactive()
        │     └── _call_tts() + _send_audio()
        │
        └── fetch-*/history-* → direct handlers (no LLM)

State: 32 module-level globals, one per responsibility
```

### Path B: AgentLoop (standalone desktop, `run.py` without `--runtime`)

```
run.py: main() → start_services() → AgentLoop.start()
  │
  ├── _run_voice_loop()
  │     └── InputManager.poll()               (VAD, returns audio_path)
  │     └── TurnRuntime.process_audio(path)
  │           ├── HTTPASRAdapter.transcribe()  (sync HTTP /asr)
  │           ├── Brain.respond()              (via ChatPipeline)
  │           │     └── AgentRuntime.run()
  │           │           ├── build_system()   (PromptBuilder)
  │           │           ├── tool_calls loop  (max 5 rounds)
  │           │           │     ├── OpenAILLMAdapter.generate()
  │           │           │     ├── ToolRegistry.execute()
  │           │           │     └── re-feed to LLM
  │           │           └── return {segments, final_reply}
  │           └── _synthesize_tts_from_segments()
  │                 ├── HTTPTTSAdapter.synthesize()
  │                 └── AsyncAudioPlayer.enqueue()
  │
  ├── _run_text_loop()
  │     └── TurnRuntime.process_text(text)    (same pipeline as voice)
  │
  └── _on_initiative() → Brain.respond() (proactive)
        └── TTS → AsyncAudioPlayer
```

State: CharacterRegistry, ToolRegistry, Brain.history, AsyncAudioPlayer

### Path C: Bridge `/runtime-ws` (partial v2, production-ready)

```
Frontend → WebSocket → /runtime-ws endpoint
  └── RuntimeWebSocketHandler
        ├── handle_text()     → Runtime.dispatch(Event(text_received))
        ├── handle_voice()    → Runtime.dispatch(Event(speech_received))
        └── handle_proactive()→ Runtime.dispatch(Event(initiative_triggered))

BUT: Runtime uses only Mock providers — never hits real LLM/TTS/ASR.
```

---

## Runtime Path (v2 target)

```
CompanionRuntime.dispatch(Event)
  │
  └── Pipeline.run(ctx)
        ├── ASRStep             (MockASR — returns "test transcription")
        ├── CharacterStep       (injects character from CharacterRegistry)
        ├── MemoryRetrieveStep  (MockMemory — returns last 10 events)
        ├── DecisionStep        (MockLLM — returns "Hello!")
        │     └── DefaultPlanner builds messages from context
        ├── ToolStep            (reads tool_calls — MockLLM never produces any)
        ├── EmotionStep         (keyword detection on reply_text)
        ├── MemorySaveStep      (MockMemory — in-memory only)
        ├── TTSStep             (MockTTS — returns 32000 empty bytes)
        └── Live2DStep          (MockLive2D — no-op)
```

---

## Divergence Points

| Concern | Bridge (/client-ws) | AgentLoop | Runtime |
|---------|--------------------|-----------|---------|
| LLM call | `OpenAILLMAdapter.generate()` (sync, Protocol) | `OpenAILLMAdapter.generate()` (sync, Protocol) | `LLMInterface.generate()` (async, ABC) — **Mock only** |
| ASR call | `HTTPASRAdapter.transcribe()` (sync) | `HTTPASRAdapter.transcribe()` (sync) | `ASRInterface.transcribe()` (async) — **Mock only** |
| TTS call | `HTTPTTSAdapter.synthesize()` (sync) | `HTTPTTSAdapter.synthesize()` (sync) | `TTSInterface.synthesize()` (async) — **Mock only** |
| Tool loop | 6-round in _call_llm_with_mcp | 5-round in AgentRuntime.run | 0-round (ToolStep runs once, no re-feed) |
| History | `_conversation_history` (module global) | `Brain.history` (instance attribute) | `Conversation` domain object |
| Memory | Compile-based (SQLite → markdown) | Store-based (SQLite memory_store) | MockMemory |
| Emotion | `_detect_tone_from_text()` in bridge | `_detect_emotion()` in turn.py | `EmotionStep._detect_emotion()` |
| State store | `app.core.state` | `app.core.state` | `app.runtime.state_store` |

---

## Key Problems

1. **Runtime has zero real providers.** The v2 pipeline is an elegant skeleton with Mock implementations for every step. No production traffic reaches it.

2. **Bridge has the most complete implementation** of the actual production flow (LLM with tool loop, TTS, ASR, memory, Live2D, history) — but it's a 1661-line monolith.

3. **AgentLoop has a second complete implementation** of the same flow — different code paths, same functionality.

4. **The `/runtime-ws` endpoint exists** and routes through `Runtime.dispatch()`, but it's a parallel path alongside the legacy `/client-ws`. No frontend connects to it.

5. **The real providers exist** (`OpenAILLMAdapter`, `HTTPASRAdapter`, `HTTPTTSAdapter`) but implement `app/models/adapters.py` Protocols, not `app/interfaces/` ABCs.

6. **The tool-calling loop** (re-feed tool results to LLM) exists in both `AgentRuntime.run()` and `_call_llm_with_mcp()` but is **missing from the v2 pipeline** — `ToolStep` writes results to state, then nothing reads them.

---

## What Phase 1 Must Do

The highest-leverage change: **wire the real providers into the Runtime so that /runtime-ws works as a production endpoint.**

This means:
- Create async wrappers around `OpenAILLMAdapter`, `HTTPASRAdapter`, `HTTPTTSAdapter` that implement `app/interfaces/` ABCs
- Register them in the ProviderRegistry
- Add the tool-calling loop to the v2 pipeline (DecisionStep → ToolStep → re-feed to LLM)
- Point the frontend at `/runtime-ws` instead of `/client-ws`

The legacy bridge remains as a fallback until Phase 3.
