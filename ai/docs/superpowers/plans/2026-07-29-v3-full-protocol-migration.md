# Runtime V2 到 V3 全量协议迁移实施计划

> **面向 AI 代理的工作者：** 必须使用 `executing-plans` 在当前项目中逐阶段实施。每个阶段严格执行红灯测试、最小实现、阶段验证、真实运行检查和独立提交；当前阶段出现回归时不得继续叠加后续阶段。

> **状态说明（2026-07-29）：** 本文件是实施时的任务清单，未回填的复选框保留为
> 历史计划记录，不再代表当前源码状态。协议迁移结论、验证结果、计划偏差和待补
> 的实机验收，以 [V3 迁移报告](../../runtime/V3_MIGRATION_REPORT.md) 为准。

**目标：** 将生产交互链从 V3 信封包裹 V2 消息，迁移为端到端强类型 V3 RuntimeEvent，并在最终阶段删除所有生产 V2 类型、flat WebSocket、兼容适配器、旧 dispatch 和 `tone`/`gesture` 业务字段 fallback。

**架构：** WebSocket Transport 只负责验证、会话顺序和发送；`EventRegistry` 将不可信 JSON 解析成强类型 V3 RuntimeEvent；`RuntimeEventHandler` 将输入事件映射到现有 `TurnInput`/`CharacterTurn`，现有 Pipeline 保持不变；`TransportEmitter` 将 CharacterTurn 转成强类型 V3 领域事件，再由每连接的 Session Writer 添加 eventId、sessionId、turnId 和 sequence。前端 `RuntimeClient` 只验证并交付 RuntimeEvent，`RuntimeEventAdapter` 将事件送入现有 Character、Audio、Session 和 UI 模块。

**技术栈：** Python 3、Pydantic 2、FastAPI WebSocket、pytest、TypeScript 5、React、Node test、Vite。

---

## 0. 不可变边界与当前基线

### 不得修改

- `frontend/electron/main.cjs` 的启动、降级和退出策略。
- `electron/process-manager.cjs`。
- `app/lifecycle/**` 和 `config/services.json`。
- TTS、GSVI、ASR 的模型加载、HTTP API 和音频编码实现。
- Live2D Cubism renderer、模型加载器和 ParameterMixer。
- `CharacterStateMachine` 的 activity 唯一所有权。
- DecisionStep、流式 LLM/TTS、AudioRuntime、ActionScheduler。

### 当前 Git 基线

- 分支：`2.5`
- 计划编写时 HEAD：`489713486308de19c98662fa27096cbe11b27f41`
- 必须保留的提交：
  - `18632ac`：Electron 启动状态重新感知。
  - `22aca9a`：可选服务故障隔离。
  - `847baac`：activity 单一所有权。
  - `3ccdee0`：退出时关闭全部托管服务。
- 已存在的部分 V3 提交：
  - `70285a8`：V3 入站外壳与 V2 适配。
  - `ce305df`：部分 V3 出站。
  - `4897134`：前端 V3 分支。

### 计划编写时测试基线

- Python 定向基线：72 passed。
- TypeScript：通过。
- 前端：28 passed、1 failed。
- 已知前端失败是 `main-performance.test.cjs` 对 `18632ac` 启动期 refresh 策略的旧断言；协议提交不得顺手修改 Electron 生产代码。每阶段必须保持“不新增失败”，最终报告单独列出该基线差异。

### 工作区保护

实施时不得暂存或提交：

```text
.claude/launch.json
data/memory/compiled/monika/facts.md
data/memory/compiled/monika/memory.md
data/memory/histories/index.json
data/memory/memory.db
data/pids/processes.json
electron/tray-icon.png
```

所有 Git 暂存必须列出精确文件，禁止 `git add -A`。

---

## 1. 迁移前后架构

### 迁移前

```text
WebSocket JSON
→ WebSocketSession 判断 V3 / V2 flat
→ V2CompatibilityAdapter
→ V3EventHandler
→ MESSAGE_TYPE_MAP
→ V2 InboundMessage
→ RuntimeEventHandler
→ TurnInput / CharacterTurn / Pipeline
→ V2 OutboundMessage 或部分 V3Emitter
→ EventEnvelope
→ RuntimeClient 双 dispatch
→ V2 EventBus 名称
→ Character / Audio / Store
```

### 迁移后

```text
WebSocket JSON
→ EventEnvelope.validate()
→ SessionEventGuard（eventId / sequence / session）
→ EventRegistry.parse()
→ Typed RuntimeEvent
→ RuntimeEventHandler
→ TurnInput(sessionId, turnId)
→ CharacterTurn / 现有 Pipeline
→ Typed DomainEvent
→ TransportEmitter
→ SessionEventWriter
→ V3 EventEnvelope
→ Frontend EventRegistry
→ RuntimeEventAdapter
├─ Session / Service module
├─ Turn / UI module
├─ CharacterController / CharacterStateMachine
└─ AudioPlayer
```

---

## 2. 最终 V3 Envelope

唯一 wire 格式：

```json
{
  "protocolVersion": "3.0",
  "eventId": "evt_...",
  "eventType": "user.text",
  "sessionId": "ses_...",
  "turnId": "turn_...",
  "sequence": 2,
  "source": "frontend",
  "timestamp": 1785312000.0,
  "payload": {
    "text": "你好"
  }
}
```

规则：

- `protocolVersion` 只接受 `"3.0"`。
- `eventId` 使用 UUID，连接内维护有界去重缓存。
- `sessionId` 由前端在 WebSocket open 时生成，`session.open` 绑定连接，服务端原样确认。
- turn-scoped 事件必须有 `turnId`；system-scoped 事件必须省略或使用空 `turnId`。
- `sequence` 从 1 开始，在同一 session 内严格递增。
- sequence 小于或等于已接收值：重复或乱序，拒绝进入 Handler。
- sequence 大于期望值：返回 `protocol.error(sequence_gap)`；本轮不新增缓冲队列。
- 重复 `eventId` 不重复执行；已有同步响应时重放缓存响应，否则作为幂等 no-op 并记录 Telemetry。
- `payload` 只在私有 JSON 边界短暂表现为 `Mapping[str, object]`/`unknown`；Registry 返回后必须是 eventType 对应的 Pydantic model 或 TypeScript discriminated union。
- 未知版本、事件名、缺少 turnId、payload 错误都返回明确 `protocol.error`。

Python 对外类型轮廓：

```python
PayloadT = TypeVar("PayloadT", bound=BaseModel)

class EventEnvelope(BaseModel, Generic[PayloadT]):
    protocol_version: Literal["3.0"] = Field(alias="protocolVersion")
    event_id: UUID = Field(alias="eventId")
    event_type: EventType = Field(alias="eventType")
    session_id: str = Field(alias="sessionId")
    turn_id: str | None = Field(default=None, alias="turnId")
    sequence: int = Field(ge=1)
    source: EventSource
    timestamp: float
    payload: PayloadT
```

TypeScript 对外类型轮廓：

```ts
export type EventEnvelope<K extends EventType = EventType> = {
  protocolVersion: '3.0'
  eventId: string
  eventType: K
  sessionId: string
  turnId?: string
  sequence: number
  source: EventSource
  timestamp: number
  payload: EventPayloadMap[K]
}
```

---

## 3. 最终 V3 事件清单

| 事件 | 方向 | Scope | 生产者 | 消费者 |
|---|---|---|---|---|
| `session.open` | F→B | system | RuntimeClient | WebSocketSession |
| `session.opened` | B→F | system | WebSocketSession | Session module |
| `session.closed` | B→F | system | WebSocketSession | Session module |
| `session.ping` / `session.pong` | 双向 | system | Session keepalive | Session keepalive |
| `runtime.status` | B→F | system | RuntimeEventHandler | Status UI |
| `runtime.ready` | Platform→F | system | Electron lifecycle snapshot adapter | Session module |
| `runtime.degraded` | Platform→F | system | Electron lifecycle snapshot adapter | Session module |
| `service.status` | Platform→F | system | Electron lifecycle snapshot adapter | Service status module |
| `configuration.updated` | B→F | system | Management handler | Settings UI |
| `protocol.error` | B→F | system/turn | Session / Registry | Error UI / request broker |
| `user.text` | F→B | turn | RuntimeClient | RuntimeEventHandler |
| `user.audio.started` | F→B | turn | AudioRecorder adapter | Audio assembler |
| `user.audio.chunk` | F→B | turn | AudioRecorder adapter | Audio assembler |
| `user.audio.completed` | F→B | turn | AudioRecorder adapter | RuntimeEventHandler |
| `user.audio.cancelled` | F→B | turn | AudioRecorder adapter | Audio assembler |
| `turn.started` | B→F | turn | TransportEmitter | Turn module / CharacterStateMachine |
| `turn.progress` | B→F | turn | Runtime status callback | Turn module |
| `turn.completed` | B→F | turn | TransportEmitter | Turn module |
| `turn.failed` | B→F | turn | TransportEmitter | Turn module / Error UI |
| `turn.cancelled` | 双向 | turn | RuntimeClient / Handler | Generation guard / Audio |
| `asr.started` | B→F | turn | RuntimeEventHandler | Turn UI |
| `asr.result` | B→F | turn | TransportEmitter | Conversation UI |
| `asr.failed` | B→F | turn | TransportEmitter | Error UI |
| `assistant.text.started` | B→F | turn | TransportEmitter | Conversation UI |
| `assistant.text.chunk` | B→F | turn | TransportEmitter（当前不发送） | Conversation UI |
| `assistant.text.completed` | B→F | turn | TransportEmitter | Conversation UI |
| `assistant.failed` | B→F | turn | TransportEmitter | Error UI |
| `character.intent` | B→F | turn | TransportEmitter | CharacterController |
| `character.expression` | B→F | turn/system | AvatarController backend | AvatarController frontend |
| `character.motion` | B→F | turn/system | AvatarController backend | AvatarController frontend |
| `character.component` | B→F | turn/system | AvatarController backend | ComponentManager |
| `character.snapshot` | B→F | system | Avatar state restore | AvatarController frontend |
| `character.suggestion` | B→F | turn/system | AvatarController backend | Permission/UI |
| `character.control.requested` | F→B | turn/system | AvatarController frontend | AvatarController backend |
| `character.suggestion.accepted` | F→B | system | Avatar UI | AvatarController backend |
| `character.suggestion.rejected` | F→B | system | Avatar UI | AvatarController backend |
| `tts.started` | B→F | turn | TransportEmitter | Audio module |
| `tts.audio` | B→F | turn | TransportEmitter | AudioPlayer |
| `tts.completed` | B→F | turn | TransportEmitter | Audio module |
| `tts.failed` | B→F | turn | TransportEmitter | Audio/Error module |
| `tts.cancelled` | B→F | turn | RuntimeEventHandler | AudioPlayer generation guard |
| `tool.requested` | B→F | turn | Tool confirmation broker | PermissionDialog |
| `tool.started` | B→F | turn | Tool coordinator | Debug/turn module |
| `tool.result` | B→F | turn | Tool coordinator | Debug/turn module |
| `tool.failed` | B→F | turn | Tool coordinator | Debug/turn module |
| `management.requested` | F→B | system | CommandBroker | ManagementHandler |
| `management.result` | B→F | system | ManagementHandler | CommandBroker |
| `management.failed` | B→F | system | ManagementHandler | CommandBroker |
| `telemetry.batch` | B→F | system/turn | TurnTelemetry adapter | DebugPanel |

决策：

- 不定义 `character.state`。activity 已由 `CharacterStateMachine` 唯一持有，重新引入该事件会恢复第二写入源。
- 不定义独立的 `service.ready` 和 `service.failed`；由 `service.status` 的强类型 `state: "starting" | "ready" | "degraded" | "failed" | "stopped"` 覆盖，避免只有订阅方没有发送方的死事件。
- 当前非流式输出只发送 `assistant.text.started` 和 `assistant.text.completed`；`assistant.text.chunk` 保留完整 schema，但本轮不实现流式生成。
- Tool 用户批准/拒绝继续使用现有 HTTP confirmation endpoint；本轮只迁移 WebSocket 上的请求和结果事件，不重写权限系统。
- 服务状态继续以现有 Electron `lifecycle:snapshot` 为权威来源；Renderer 平台适配器把 snapshot 投影为 typed `runtime.ready/degraded` 和 `service.status`，不修改 LifecycleOrchestrator，也不新建服务状态 WebSocket。
- `assistant.text.chunk` 在本轮仅作为 schema 能力存在，不注册运行时订阅者；等未来真正流式输出有发送方时再接入，避免制造“只有订阅方、没有发送方”的死路径。

---

## 4. V2→V3 迁移矩阵

| V2 类型/事件 | 当前使用位置 | V3 替代 | 阶段 | 最终删除位置 |
|---|---|---|---|---|
| `TextInput` / `text_input` | Python protocol、TS protocol/client | `user.text` | V3-2 | `app/transport/protocol.py`、`frontend/src/runtime/protocol.ts` |
| `AudioInput` / `audio_input` | Handler buffer、TS recorder send | `user.audio.started/chunk` | V3-2 | 同上 |
| `AudioEnd` / `audio_end` | Handler audio completion | `user.audio.completed` | V3-2 | 同上 |
| `Interrupt` / `interrupt` | Handler、TS client | `turn.cancelled`、`user.audio.cancelled` | V3-2/V3-4 | 同上 |
| `Ping` / `Pong` | Session flat keepalive | `session.ping/pong` | V3-1/V3-2 | V2 protocol 与 flat `_ping_loop` |
| `Command` / `command` | ManagementHandler、CommandBroker | `management.requested` | V3-2/V3-3 | V2 protocol、旧 command dispatch |
| `CommandResponse` | ManagementHandler、前端 broker | `management.result/failed` | V3-3/V3-4 | V2 protocol、EventMap |
| `AvatarRequestMsg` | Avatar frontend/backend | `character.control.requested` | V3-2/V3-3 | V2 avatar transport map |
| `AvatarAcceptMsg` | Avatar frontend/backend | `character.suggestion.accepted` | V3-2 | V2 avatar transport map |
| `AvatarRejectMsg` | Avatar frontend/backend | `character.suggestion.rejected` | V3-2 | V2 avatar transport map |
| `AssistantMessage` | V2 emitter、TS dispatch | `assistant.text.completed` | V3-3/V3-4 | V2 protocol/emitter/frontend protocol |
| `AssistantChunk` | V2 protocol、TS dispatch | `assistant.text.chunk` | V3-3/V3-4 | 同上 |
| `UserMessage` | ASR result push | `asr.result` | V3-3/V3-4 | 同上 |
| `TtsStart` / `tts_start` | Emitter、EventBus | `tts.started` | V3-3/V3-4 | 同上 |
| `TtsAudio` / `tts_audio` | Emitter、AudioPlayer dispatch | `tts.audio` | V3-3/V3-4 | 同上 |
| `TtsEnd` / `tts_end` | Emitter、interrupt、EventBus | `tts.completed/cancelled/failed` | V3-3/V3-4 | 同上 |
| `RuntimeStatus` | Handler、Emitter、Status UI | `runtime.status` / `turn.progress` | V3-3/V3-4 | 同上 |
| `ToolConfirmation` | Tool broker、PermissionDialog | `tool.requested` | V3-3/V3-4 | V2 protocol |
| `CharacterUpdate` | V2 emitter、frontend | `character.intent` | V3-3/V3-4 | V2 protocol/emitter |
| `SessionEvent` / `session` | Session init | `session.opened`、`configuration.updated` | V3-1/V3-3 | V2 protocol、旧 dispatch |
| `Error` / `error` | Handler、Management | `protocol.error`、turn/assistant/tts/tool failed | V3-1/V3-3 | V2 protocol |
| Avatar component/expression/motion/state | `app/avatar/protocol.py`、client dispatch | `character.component/expression/motion/snapshot` | V3-3/V3-4 | flat Avatar message类型 |
| `telemetry` | client、DebugPanel | `telemetry.batch` | V3-3/V3-4 | 旧 dispatch |
| `runtime:tts_start/end` | TS EventMap | canonical RuntimeEvent adapter callbacks | V3-4 | `frontend/src/core/event-bus.ts` |
| `runtime:character_intent` | TS EventMap/controllers | `character.intent` typed adapter output | V3-4 | 旧 EventMap 键 |
| `tone` segment 字段 | prompt、character_intent fallback、历史结构化 JSON | `emotion` | V3-5/V3-6 | prompt/fallback/迁移后数据 |
| `gesture` segment 字段 | prompt、character_intent fallback、历史结构化 JSON | `behavior` | V3-5/V3-6 | prompt/fallback/迁移后数据 |
| V2 flat WebSocket | `WebSocketSession`、frontend client | 只接受 EventEnvelope | V3-2/V3-4 | `v2_adapter.py`、`compat.ts` |
| V3→V2 inbound | `V3EventHandler._handle_turn()` | Registry→RuntimeEvent | V3-2 | `MESSAGE_TYPE_MAP` 转换 |
| V2→V3 outbound | `_v2_to_envelope()`、Session `_send()` | DomainEvent→SessionEventWriter | V3-3 | V2 serialize/wrapper |
| 历史角色消息 JSON | `data/memory/histories`、startup migration | SQLite V3 schema/只读 archive | V3-5 | runtime startup legacy importer |
| Turn diagnostics | `turns.db.detail_json` | versioned V3 detail JSON | V3-5 | 无版本 detail JSON |
| DebugPanel diagnostics | V2 assistant diagnostics/telemetry | `telemetry.batch` + management query | V3-3/V3-4 | assistant payload diagnostics |

不属于 Runtime V2 协议、不得机械改名的命中：

- `GSVIV2Config` / `gsvi-v2pro`：模型产品名称。
- Cubism SDK 中的 compatibility 注释。
- browser “user gesture”：浏览器自动播放术语。
- `VADGestureController`、Avatar motion category `"gesture"`：角色动作领域概念；最终搜索报告单独分类。
- OpenAI-compatible、Cloud TTS compatible：第三方 API 兼容性描述。

---

## 5. 文件职责

### 创建

- `contracts/v3/events.py`：全部 Pydantic payload 和 RuntimeEvent 类型。
- `contracts/v3/registry.py`：eventType→payload model 注册、解析和错误。
- `contracts/v3/runtime-events.schema.json`：从 Pydantic 导出的跨端 contract。
- `scripts/export_v3_contract.py`：生成/校验 JSON schema。
- `frontend/src/runtime/event-types.ts`：TypeScript EventPayloadMap 与 discriminated union。
- `frontend/src/runtime/registry.ts`：unknown JSON→typed EventEnvelope 校验。
- `tests/test_v3_event_registry.py`：后端 schema/registry 测试。
- `tests/test_v3_session_protocol.py`：会话、幂等、顺序和错误测试。
- `tests/test_v3_runtime_handler.py`：入站、turn context、取消和 stale turn。
- `tests/test_v3_transport_emitter.py`：出站顺序和 identity。
- `tests/test_v3_data_migration.py`：数据备份、迁移、幂等和自然语言保护。
- `tests/test_v3_architecture_boundaries.py`：禁止生产 V2 类型和 compat。
- `frontend/src/runtime/registry.test.ts`：前端 Envelope/payload 校验。
- `frontend/src/runtime/client.test.ts`：V3-only 收发、重连和 sequence。
- `frontend/src/runtime/adapter.test.ts`：事件模块路由和 stale generation。
- `scripts/migrate_runtime_data_v3.py`：一次性数据迁移。
- `docs/runtime/V3_PROTOCOL.md`：最终事件清单、顺序和错误策略。
- `docs/runtime/V3_MIGRATION_REPORT.md`：数据与删除结果。

### 修改

- `contracts/v3/envelope.py`
- `contracts/v3/__init__.py`
- `app/transport/session.py`
- `app/transport/v3_handler.py`
- `app/transport/v3_emitter.py`（随后合并进 canonical emitter）
- `app/transport/emitter.py`
- `app/transport/websocket/handler.py`
- `app/transport/management.py`
- `app/bridge/server.py`
- `app/avatar/protocol.py`
- `app/runtime/character_turn.py`
- `app/runtime/runtime.py`
- `app/runtime/character_intent.py`
- `app/providers/memory/sqlite_memory.py`
- `app/prompts/utils/output_format.txt`
- `app/interfaces/llm.py`
- `frontend/src/runtime/envelope.ts`
- `frontend/src/runtime/client.ts`
- `frontend/src/runtime/adapter.ts`
- `frontend/src/runtime/RuntimeEvent.ts`
- `frontend/src/core/event-bus.ts`
- `frontend/src/session/DesktopSessionProvider.tsx`
- `frontend/src/character/AvatarController.ts`
- `frontend/src/character/controllers.ts`
- `frontend/src/ui/DebugPanel.tsx`
- `frontend/src/ui/DeveloperWorkspace.tsx`
- `frontend/src/ui/PermissionDialog.tsx`
- `frontend/package.json`
- 相关 Python/TypeScript 测试。

### 最终删除

- `app/transport/protocol.py`
- `app/transport/v2_adapter.py`
- `contracts/v3/compat.py`
- `frontend/src/runtime/protocol.ts`
- `frontend/src/runtime/compat.ts`
- V2-only 测试断言和测试 fixture。

---

## 6. Phase V3-1：Schema 与 Registry

**提交目标：** 建立 canonical camelCase Envelope、完整强类型 payload、Registry 和跨端 schema；现有运行路径在本阶段只做字段适配，不删除 Handler。

### 测试先行

- [ ] 创建 `tests/test_v3_event_registry.py`，覆盖：
  - canonical 九个 Envelope 字段。
  - 所有事件 round-trip。
  - system 事件无 turnId。
  - turn 事件缺 turnId。
  - unknown version/event。
  - payload 缺字段、错类型、额外未知字段。
  - `character.state` 不在注册表。
- [ ] 创建 `frontend/src/runtime/registry.test.ts`，对同一组 JSON fixture 执行 parse。
- [ ] 增加 schema 对齐测试：Python 导出 schema 与 `runtime-events.schema.json` 完全一致；前端事件名和 required field 表与 schema 一致。
- [ ] 运行红灯：

```powershell
C:\ProgramData\miniconda3\envs\qwen3-asr\python.exe -m pytest -q -p no:cacheprovider tests/test_v3_event_registry.py
node --test --experimental-strip-types src/runtime/registry.test.ts
```

预期：缺少 Registry、camelCase Envelope 和事件 payload，测试失败。

### 最小实现

- [ ] 在 `contracts/v3/events.py` 为每个事件定义 `extra="forbid"` 的 Pydantic payload。
- [ ] 在 `contracts/v3/registry.py` 使用明确 `EVENT_MODELS` 字典解析；未知事件抛出 `UnsupportedEventError`。
- [ ] 修改 `contracts/v3/envelope.py`，只在 `model_dump(by_alias=True)` 输出 canonical wire 字段。
- [ ] 删除 `LEGACY_VERSIONS`；`2.0` 与所有未知版本统一拒绝。
- [ ] `scripts/export_v3_contract.py --write` 生成 schema；`--check` 只比较、不写文件。
- [ ] 在 TS 创建 `EventPayloadMap`、`RuntimeEventEnvelope` 和逐事件 validator；不得使用 `any`。
- [ ] 修改现有 session/client 的 Envelope 字段访问，使当前应用在 canonical Envelope 下仍可通信；V2 payload 分支暂时保留到后续阶段。
- [ ] `session.open/opened`、`session.ping/pong`、`protocol.error` 首先切换到 canonical eventType。

### 验证

```powershell
C:\ProgramData\miniconda3\envs\qwen3-asr\python.exe -m pytest -q -p no:cacheprovider tests/test_v3_event_registry.py tests/test_contract_v3_protocol.py
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
```

验收：

- 新 Registry 测试全部通过。
- 现有 Python protocol tests 根据 canonical V3 更新后通过。
- 前端相对基线不新增失败。

### 提交

```powershell
git add contracts/v3/envelope.py contracts/v3/events.py contracts/v3/registry.py contracts/v3/runtime-events.schema.json contracts/v3/__init__.py scripts/export_v3_contract.py tests/test_v3_event_registry.py tests/test_contract_v3_protocol.py frontend/src/runtime/envelope.ts frontend/src/runtime/event-types.ts frontend/src/runtime/registry.ts frontend/src/runtime/registry.test.ts frontend/src/runtime/client.ts frontend/package.json
git commit -m "feat(protocol): define canonical V3 event registry"
```

---

## 7. Phase V3-2：后端入站

**提交目标：** 生产 WebSocket 只接受 V3；Handler 直接接收 typed RuntimeEvent；sessionId/turnId 进入 CharacterTurn；删除 V3→V2 入站往返。

### 测试先行

- [ ] 创建 `tests/test_v3_session_protocol.py`：
  - V2 flat JSON 返回 `protocol.error(unsupported_protocol)`.
  - duplicate eventId 不重复调用 Handler。
  - sequence 重复、倒退、缺口被拒绝并记录。
  - reconnect 使用新 session 后 sequence 重置。
- [ ] 创建 `tests/test_v3_runtime_handler.py`：
  - `user.text` 生成 `TurnInput(text, session_id, turn_id)`。
  - audio started/chunks/completed 顺序和单一 turnId。
  - audio chunk 未 started、跨 turn chunk、重复 completed 被拒绝。
  - `turn.cancelled` 取消 active generation。
  - stale turn 在 `runtime.handle_turn()` 前拒绝。
  - management 和 Avatar V3 输入不使用 V2 dataclass。
- [ ] 红灯命令：

```powershell
C:\ProgramData\miniconda3\envs\qwen3-asr\python.exe -m pytest -q -p no:cacheprovider tests/test_v3_session_protocol.py tests/test_v3_runtime_handler.py
```

预期：flat V2 仍被接受、Handler 仍导入 `InboundMessage`、turn context 未传播。

### 最小实现

- [ ] `WebSocketSession` 删除 V2 分支，只执行 Envelope→SessionGuard→Registry→Handler。
- [ ] Session 不再覆盖客户端 sequence；按 session 严格验证。
- [ ] 添加有界 eventId 响应缓存，最大 1024 项，断开连接即释放。
- [ ] `RuntimeEventHandler.handle()` 改为接收 `RuntimeEventEnvelope`。
- [ ] 将音频 buffer 绑定到 `sessionId + turnId`。
- [ ] 修改 `TurnInput` 增加 `session_id`、`turn_id`；`CharacterRuntime` 优先使用输入 identity，initiative 未提供时才生成。
- [ ] 将 text/audio pipeline 执行放入 Handler 持有的 active task，使 Session 能继续接收取消事件；不得新增第二个 EventBus。
- [ ] generation guard 在发出每个完成事件前检查 active turn。
- [ ] 前端发送方法同步改为 `user.text`、`user.audio.*`、`turn.cancelled`、`management.requested` 和 character control V3 事件。
- [ ] 删除 `app/transport/v2_adapter.py`。
- [ ] 删除 `V3EventHandler._handle_turn()` 中 `MESSAGE_TYPE_MAP`、`InboundMessage` 和 `_envelope_to_inbound` 等效逻辑。

### 验证

```powershell
C:\ProgramData\miniconda3\envs\qwen3-asr\python.exe -m pytest -q -p no:cacheprovider tests/test_v3_session_protocol.py tests/test_v3_runtime_handler.py tests/test_runtime_pipeline.py tests/test_character_turn_v3.py tests/test_command_request_correlation.py
npm.cmd run typecheck
```

阶段真实检查：

1. 启动现有服务和 Electron。
2. 发送一条文字输入，确认 Pipeline 收到与前端一致的 sessionId/turnId。
3. 用 WebSocket 发送 V2 `{"type":"text_input"}`，确认明确拒绝且不创建回合。
4. 退出 Electron，确认无残留。

### 提交

```powershell
git add app/transport/session.py app/transport/v3_handler.py app/transport/websocket/handler.py app/runtime/character_turn.py app/runtime/runtime.py app/bridge/server.py frontend/src/runtime/client.ts frontend/src/character/AvatarController.ts tests/test_v3_session_protocol.py tests/test_v3_runtime_handler.py tests/test_character_turn_v3.py tests/test_command_request_correlation.py
git rm app/transport/v2_adapter.py
git commit -m "feat(protocol): migrate runtime ingress to V3"
```

---

## 8. Phase V3-3：后端出站

**提交目标：** CharacterTurn、Management、Tool 和 Avatar 只产生 typed V3 DomainEvent；Session Writer 是唯一 Envelope/sequence 生成者；删除 V2 OutboundMessage 主路径。

### 测试先行

- [ ] 创建 `tests/test_v3_transport_emitter.py`：
  - 文字成功顺序：

```text
turn.started
assistant.text.started
assistant.text.completed
character.intent
turn.completed
runtime.status
```

  - 语音成功包含 `asr.started/result` 和严格 TTS 顺序。
  - TTS 失败只产生 `tts.failed`，文字回合仍可完成。
  - turn failure、cancel、tool、management、Avatar 事件各有明确类型。
  - 同一回合 sessionId/turnId 一致。
  - 同 session sequence 单调，跨 session 独立。
  - eventId 全部唯一。
  - assistant payload 不包含 diagnostics。
- [ ] 更新 `tests/test_transport_emitter_v3.py`，删除 V2 message 期望。
- [ ] 红灯运行：

```powershell
C:\ProgramData\miniconda3\envs\qwen3-asr\python.exe -m pytest -q -p no:cacheprovider tests/test_v3_transport_emitter.py tests/test_transport_emitter_v3.py
```

### 最小实现

- [ ] 将 canonical `TransportEmitter` 改为输出 typed DomainEvent，不构造 WebSocket JSON。
- [ ] 新建每连接 `SessionEventWriter`，唯一负责 eventId、sessionId、sequence、timestamp 和发送锁。
- [ ] 删除 `V3Emitter.SEQUENCE` 模块全局变量。
- [ ] Runtime status callback 映射为 `turn.progress`；系统服务状态使用 `runtime.status`。
- [ ] ASR、Assistant、TTS、Character、Tool 和失败事件分别建模。
- [ ] 保持 TTS 音频为当前 base64 WAV 和 volume array，不修改 AudioPlayer。
- [ ] 将 assistant diagnostics 移到 `telemetry.batch` 或显式 management query。
- [ ] ManagementHandler 返回 `management.result/failed` typed event。
- [ ] Avatar push callback 返回 `character.*` typed event。
- [ ] 主动发言复用相同 emitter，`turn.started.payload.origin="initiative"`。
- [ ] `WebSocketSession.send()` 只接受 typed DomainEvent/EventEnvelope；删除 V2 serialize wrapper。
- [ ] 删除 `OutboundMessage`、AssistantMessage、CharacterUpdate、RuntimeStatus、TTS V2 类型。

### 验证

```powershell
C:\ProgramData\miniconda3\envs\qwen3-asr\python.exe -m pytest -q -p no:cacheprovider tests/test_v3_transport_emitter.py tests/test_transport_emitter_v3.py tests/test_user_views_and_turn_recorder.py tests/test_runtime_pipeline.py
npm.cmd run typecheck
```

阶段真实检查：

- 文字输入完成一次 LLM→TTS→Live2D。
- 固定音频完成一次 ASR→LLM→TTS→Live2D。
- TTS 服务不可用时，assistant text 和 character intent 仍到达前端。

### 提交

```powershell
git add app/transport/emitter.py app/transport/v3_emitter.py app/transport/session.py app/transport/websocket/handler.py app/transport/management.py app/avatar/protocol.py app/bridge/server.py contracts/v3/events.py tests/test_v3_transport_emitter.py tests/test_transport_emitter_v3.py tests/test_user_views_and_turn_recorder.py
git commit -m "feat(protocol): emit V3 domain events directly"
```

---

## 9. Phase V3-4：前端纯 V3 消费

**提交目标：** RuntimeClient 只解析 V3 并调用 typed adapter；删除 V2 dispatch、V2 protocol 类型和 payload 恢复；Character/Audio/Store 保持现有实现。

### 测试先行

- [ ] 创建 `frontend/src/runtime/client.test.ts`：
  - V2 flat frame 被拒绝。
  - unknown version/event/payload 发出 protocol error UI 事件。
  - eventId duplicate 和 sequence out-of-order 不重复消费。
  - reconnect 生成新 sessionId 并重置 sequence。
- [ ] 创建 `frontend/src/runtime/adapter.test.ts`：
  - session/service→服务状态。
  - turn→turn manager/CharacterStateMachine。
  - character.intent→CharacterController，并携带 turnId。
  - tts.audio→现有 AudioPlayer path。
  - turn.cancelled/tts.cancelled→audio stop generation guard。
  - stale turn 的 assistant/character/tts 事件全部不生效。
  - management.result 按 requestId 解析 CommandBroker。
  - telemetry.batch 只进入 DebugPanel。
- [ ] 更新 `frontend/package.json` 将三个测试加入 `npm test`。
- [ ] 红灯：

```powershell
npm.cmd test
```

预期：client 仍导入 V2 protocol/compat，存在双 dispatch。

### 最小实现

- [ ] RuntimeClient 只负责 connect/reconnect、Envelope validate、send 和 `onEvent(event)`。
- [ ] RuntimeEventAdapter 负责按 eventType 调用现有 eventBus/模块端口。
- [ ] Electron 平台适配器将现有 `lifecycle:snapshot` 转成 typed `runtime.ready/degraded` 和 `service.status` 后交给 RuntimeEventAdapter；不改 Electron main 或 LifecycleOrchestrator。
- [ ] 删除 `dispatchV3Payload()` 中全部 V2 case。
- [ ] 删除 onmessage 的 flat V2 检测和 `v2ToV3Envelope()`。
- [ ] 删除 `OutboundMessage` 泛型 send API；只暴露 typed sendText/sendAudio/cancel/management/avatar 方法。
- [ ] 将旧 EventMap 名称改为职责明确的 typed 内部事件，不恢复 `runtime:character_state`。
- [ ] `turn.started` 将 turnId 设置到 CharacterController/CharacterStateMachine。
- [ ] React Store 只订阅 `character:activity` 镜像，不直接依据 runtime.status 改 activity。
- [ ] AudioPlayer 继续使用现有 queue/playbackGeneration；取消事件调用现有 stop，不重写播放器。
- [ ] DebugPanel 从 telemetry.batch 和 management diagnostics 读取，不再读取 assistant diagnostics。
- [ ] PermissionDialog 消费 `tool.requested`，现有 HTTP approve/reject 不变。
- [ ] 删除 `frontend/src/runtime/protocol.ts` 和 `compat.ts`。

### 验证

```powershell
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
```

真实检查：

- 文本、语音、音频播放、Live2D expression/motion/lip-sync。
- speaking 中点击打断：当前音频立即停止；随后到达的旧 turn 事件被 generation guard 拒绝。
- HistoryPanel、DebugPanel、DeveloperWorkspace 和 PermissionDialog 可用。

### 提交

```powershell
git add frontend/src/runtime/client.ts frontend/src/runtime/adapter.ts frontend/src/runtime/RuntimeEvent.ts frontend/src/runtime/event-types.ts frontend/src/runtime/registry.ts frontend/src/runtime/client.test.ts frontend/src/runtime/adapter.test.ts frontend/src/core/event-bus.ts frontend/src/session/DesktopSessionProvider.tsx frontend/src/character/controllers.ts frontend/src/character/AvatarController.ts frontend/src/ui/DebugPanel.tsx frontend/src/ui/DeveloperWorkspace.tsx frontend/src/ui/PermissionDialog.tsx frontend/package.json
git rm frontend/src/runtime/protocol.ts frontend/src/runtime/compat.ts
git commit -m "feat(frontend): consume V3 runtime events only"
```

---

## 10. Phase V3-5：数据迁移

**提交目标：** 一次性升级结构化旧字段和诊断格式；从 runtime startup 删除长期 legacy importer；自然语言内容和历史 archive 不做错误替换。

### 数据范围

- `data/memory/memory.db`
  - 只检查结构化 JSON 列：`character_states.state_json`、`retrieval_audit.result_json`、`usage_events.context_json`。
  - 不改 `facts.fact`、`logs.content`、`memories.content` 等自然语言。
- `data/runtime/turns.db`
  - `turn_traces.detail_json` 增加 `schemaVersion: 3`。
  - structured keys `tone→emotion`、`gesture→behavior`。
- `data/memory/histories/*.json`
  - role/content 历史不属于 transport payload，不替换自然语言。
  - 迁移完成后保留只读 `v2-archive`，runtime 不再扫描导入。
- `memory.v2-backup.db`
  - 作为历史备份保留，不作为运行数据源。
- 诊断 ZIP/JSONL/缓存
  - 只迁移存在且可识别的 structured payload；不存在时在报告中记录“未发现”。
- prompt/config
  - `output_format.txt` 改成 emotion/behavior。

### 测试先行

- [ ] 创建 `tests/test_v3_data_migration.py`：
  - migration 先生成 timestamped backup 和 SHA-256 manifest。
  - 事务失败时原 DB 不变。
  - structured JSON key 正确转换。
  - 用户正文中的单词 tone/gesture 原样保留。
  - 二次执行幂等。
  - schema marker 更新。
  - 已迁移历史不再被 startup importer 重复扫描。
- [ ] 红灯：

```powershell
C:\ProgramData\miniconda3\envs\qwen3-asr\python.exe -m pytest -q -p no:cacheprovider tests/test_v3_data_migration.py tests/test_history_migration_v3.py tests/test_memory_turn_idempotency_v3.py
```

### 最小实现

- [ ] `scripts/migrate_runtime_data_v3.py --dry-run` 输出文件、表、行数和校验，不写入。
- [ ] `--apply` 先复制备份，再在 SQLite transaction 中迁移。
- [ ] 写入 `data/migrations/v3-protocol-<timestamp>.json` manifest；该 manifest 包含路径、原/新 checksum、迁移行数，不包含用户正文。
- [ ] 将 history import 变成脚本显式步骤，从 `sqlite_memory.py` startup 删除 `migrate_legacy_histories()`。
- [ ] 更新 turn recorder 输出 `schemaVersion: 3`。
- [ ] 更新 prompt、LLM segment contract 和 `character_intent.py`，只读取 emotion/behavior。
- [ ] 对真实数据先 dry-run，人工核对数量后 apply；不将实际 Memory DB 和用户数据提交。

### 验证

```powershell
C:\ProgramData\miniconda3\envs\qwen3-asr\python.exe scripts/migrate_runtime_data_v3.py --dry-run
C:\ProgramData\miniconda3\envs\qwen3-asr\python.exe -m pytest -q -p no:cacheprovider tests/test_v3_data_migration.py tests/test_history_migration_v3.py tests/test_memory_turn_idempotency_v3.py tests/test_user_views_and_turn_recorder.py
```

执行真实 `--apply` 前再次确认备份目标位于 `data/backups/v3-protocol/`，不得删除 `memory.v2-backup.db`。

### 提交

提交脚本、schema、测试和文档，不提交实际数据库、备份或用户历史：

```powershell
git add scripts/migrate_runtime_data_v3.py app/providers/memory/sqlite_memory.py app/runtime/turn_recorder.py app/runtime/character_intent.py app/prompts/utils/output_format.txt app/interfaces/llm.py tests/test_v3_data_migration.py tests/test_history_migration_v3.py tests/test_memory_turn_idempotency_v3.py tests/test_user_views_and_turn_recorder.py docs/runtime/V3_MIGRATION_REPORT.md
git commit -m "feat(data): migrate persisted runtime data to V3"
```

---

## 11. Phase V3-6：删除 V2 与架构守卫

**提交目标：** 删除所有生产 V2 定义、compat 和旧字段 fallback；架构测试阻止回归。

### 测试先行

- [ ] 创建 `tests/test_v3_architecture_boundaries.py`，扫描 `app/`、`contracts/v3/` 和 `frontend/src/runtime/`：
  - 禁止 import `app.transport.protocol`。
  - 禁止 `InboundMessage`、`OutboundMessage`、`parse_inbound`。
  - 禁止 `v2_adapter`、`contracts.v3.compat`、frontend `compat.ts`。
  - 禁止 wire event：`text_input`、`audio_input`、`audio_end`、`assistant_message`、`character_update`、`runtime_status`、`tts_start`、`tts_audio`、`tts_end`。
  - 禁止生产 segment fallback `tone`/`gesture`。
  - 禁止 `protocolVersion: "2.0"`。
  - 禁止 Session 接受无 Envelope JSON。
- [ ] 守卫明确排除：
  - `scripts/migrate_runtime_data_v3.py`
  - `docs/runtime/V3_MIGRATION_REPORT.md`
  - 历史 fixture 目录
  - GSVI v2pro 模型名称
  - Cubism SDK 和 browser gesture 术语
- [ ] 先运行守卫，确认被剩余 V2 文件触发。

### 删除和收口

- [ ] 删除 `app/transport/protocol.py`。
- [ ] 删除 `contracts/v3/compat.py`。
- [ ] 删除残留 V2 emitter、serialize/deserialize、Message Type Map。
- [ ] 删除 V2-only 测试或将有价值测试改为 V3 fixture。
- [ ] 清理文档中把 V2 Transport 描述为正式协议的内容。
- [ ] 更新 `ARCHITECTURE.md` 和 `docs/runtime/V3_PROTOCOL.md`。
- [ ] 执行最终搜索并逐项分类：

```powershell
git grep -n -I -E "V2|protocol.?v2|OutboundMessage|InboundMessage|tone|gesture|character_update|assistant_message|tts_start|tts_audio|tts_end|compat|legacy|fallback|dispatchV2|parse_inbound" -- app contracts frontend/src config scripts tests docs
```

生产协议命中必须为零；非协议命中必须记录文件、语义和保留理由。

### 自动化验证

```powershell
C:\ProgramData\miniconda3\envs\qwen3-asr\python.exe -m pytest -q -p no:cacheprovider
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
git diff --check
```

相对计划基线：

- Python 不得新增失败。
- TypeScript/build 必须通过。
- 前端不得新增失败；已知 Electron test 差异单独报告，不在协议提交中修改生产启动逻辑。

### 真实验收

按顺序执行并保存 eventId/sessionId/turnId/sequence 日志：

1. Electron 启动，Backend 监听，Live2D 显示。
2. 文字输入→LLM→TTS→AudioPlayer→Live2D。
3. 固定音频→ASR→LLM→TTS→AudioPlayer→Live2D。
4. 麦克风语音回合。
5. speaking 中打断，记录旧 turn 事件被拒绝。
6. TTS/GSVI 故障降级，文字模式继续完成。
7. 主动发言完整回合。
8. 至少一个工具请求/批准/结果。
9. Memory 保存、重启后读取。
10. 三次 Electron 启动→托盘退出，无残留 Electron、Node、Lifecycle client、ASR、TTS、GSVI。

任何一项失败：修复 V3-6 当前提交，不进入 AudioRuntime、流式输出或 Live2D 重构。

### 提交

```powershell
git add tests/test_v3_architecture_boundaries.py ARCHITECTURE.md docs/runtime/V3_PROTOCOL.md docs/runtime/V3_MIGRATION_REPORT.md
git rm app/transport/protocol.py contracts/v3/compat.py
git commit -m "refactor(protocol): remove V2 runtime protocol"
```

提交前用 `git diff --cached --name-only` 核对没有 data、模型、Electron 启动或生命周期文件。

---

## 12. 每阶段停止条件

以下任一条件出现时，停止当前阶段并修复，不继续提交下一阶段：

- Electron 无法进入主界面。
- Backend `/client-ws` 无法连接。
- TTS/ASR 进程未创建或模型未加载。
- 文字模式因可选语音服务失败而不可用。
- Live2D 不显示或 activity 出现第二写入源。
- 同一 turn 的 sessionId/turnId 不一致。
- sequence 不单调或 eventId 重复导致业务重复执行。
- stale turn 的 TTS、Character 或 Assistant 事件仍生效。
- Memory 用户数据被脚本错误修改。
- 当前阶段引入新的自动化失败。

---

## 13. 最终报告模板

最终完成报告必须包含：

1. 迁移前后架构图。
2. 实际启用的完整 V3 事件清单及 producer/consumer。
3. 删除的 V2 类型、文件和转换函数。
4. 数据迁移文件、备份、checksum、迁移行数和废弃项。
5. V3-1 至 V3-6 每阶段提交 SHA。
6. 真实日志中的 sessionId/turnId/sequence/eventId 全链证据。
7. 文字、固定音频、麦克风、打断、降级、主动发言、工具结果。
8. 全项目剩余 V2 搜索结果及非协议命中的保留理由。
9. Python、前端、构建、Electron 和进程清理回归结果。
10. 明确回答是否满足“V3 唯一生产协议”。

只有生产 WebSocket 只收发 V3、Handler/Pipeline/Emitter/Frontend 不使用 V2、compat 已删除、旧数据已迁移或归档、真实文字与语音回合通过时，才允许结论为“V3 全迁移完成”。
