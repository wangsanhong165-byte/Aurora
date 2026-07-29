# Architecture — CharacterTurn Runtime V3

> Date: 2026-07-29
> Branch: `2.5`
> This document describes the current implementation. Code and tests remain authoritative.

## Runtime ownership

Every text, speech, or initiative interaction is converted to a typed `TurnInput`.
`CharacterRuntime.handle_turn()` is the only public turn entry point and returns a
`CharacterTurn` with a stable `turn_id`, explicit phase, typed transient fields,
`TurnOutput`, metrics, warnings, and a structured `TurnError`.

```text
TurnInput
  → CharacterRuntime.handle_turn()
  → CharacterTurn (created → processing)
  → ASR → Character → Memory retrieval → Decision
  → Emotion → Memory commit → TTS → PerformancePlan
  → completed | failed
```

The former `CompanionRuntime.dispatch(Event)`, mutable `Context.state`,
`ChatPipeline`, and file-history save step no longer exist. The module-level
`runtime: CharacterRuntime` remains the composition root.

`CharacterSelf` owns durable character state. A turn may read a snapshot and
stage a `CharacterSelfChange`; durable changes only take effect through
`CharacterSelf.commit()`.

## Decision and performance boundaries

`PromptCompiler` creates a detached model request from the turn, character
aggregate, memories, conversation, and tool schemas. It performs no I/O and
does not mutate the turn.

`ResponseInterpreter` converts canonical `LLMResponse` data into reply text,
segments, tool calls, and `PerformancePlan`. Renderer-specific keys are removed
and reported through turn warnings.

`PerformancePlan` contains only semantic fields:

- `emotion`
- `behavior`
- `attention`
- `energy`
- `speaking`
- `duration_ms`
- `context_tags`

The backend never sends Cubism parameters, expression filenames, motion files,
or model identifiers as part of a Runtime presentation update.

## Transport

`contracts/v3/envelope.py`, `contracts/v3/events.py`, and
`contracts/v3/registry.py` are the canonical server-side protocol sources.
`/client-ws` is the only WebSocket route. `WebSocketSession` validates the
V3 envelope, session identity, `eventId`, and contiguous inbound sequence
before `RuntimeEventHandler` maps an event to
`CharacterRuntime.handle_turn()`. The old bridge Runtime handler, V2 protocol
module, compatibility adapter, and duplicate WebSocket routes were removed.

`TransportEmitter` is the only normal turn-to-domain-event emitter. It never
constructs WebSocket JSON; the connection-local session writer is the only
owner of outbound `eventId`, `sessionId`, `sequence`, timestamp, and send
serialization:

```text
success:
turn.started
→ [asr.started → asr.result]
→ [tool.started → tool.result | tool.failed]
→ assistant.text.started → assistant.text.completed
→ [tts.started → tts.audio → tts.completed | tts.failed]
→ character.intent
→ turn.completed
→ runtime.status(idle)

failure:
turn.failed → runtime.status(idle)
```

`character.intent` is renderer independent. The frontend resolves it through:

```text
CharacterBehaviorResolver
→ CharacterPerformancePolicy
→ ParameterMixer
→ Live2DModelAdapter
→ Cubism SDK
```

Explicit user Avatar management messages remain a separate permission-controlled
channel. They are not emitted by Runtime decisions.

## Memory and history

SQLite schema version 4 adds `turn_id`, `write_token`, and `history_uid` to
conversation logs plus a `turn_commits` table. `MemorySaveStep` commits a turn
with the unique key `(character_id, turn_id, write_token)`. Replaying the same
write returns without inserting duplicate user or assistant rows.

The first V3 migration creates `memory.v2-backup.db` beside the existing
database. Schema migration is repeatable and retains legacy rows with nullable
V3 identifiers.

Conversation messages are written only to SQLite. The history JSON directory is
read-only legacy input/fallback; Runtime no longer appends conversation turns to
JSON. The lightweight index remains for history list metadata.

## Initiative scheduling

Initiative producers only create `InitiativeCandidate` values. Each candidate
has a stable ID, source, normalized topic fingerprint, priority, freshness,
expiry, timestamp, and payload.

`CharacterRuntime` owns the queue:

- duplicate topics collapse to the newer/higher-scored candidate;
- expired candidates are discarded;
- candidates remain queued while a turn is processing or speaking;
- one candidate is selected only while Runtime is idle;
- the selected candidate becomes a normal `TurnInput(origin=initiative)` and
  uses the same Decision, Memory, TTS, transport, and performance path.

Initiative never interrupts an active user or speech turn.

## Service configuration

`config/services.json` is the single checked-in service-port source:

| Service | Port |
|---|---:|
| ASR | 9101 |
| LLM | 9102 |
| TTS | 9103 |
| Memory | 9104 |
| GSVI | 9105 |
| Bridge | 9528 |
| Vite frontend | 5173 |

Environment variables may override configured values at runtime.
