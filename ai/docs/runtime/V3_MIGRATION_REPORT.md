# V2 → V3 全量迁移报告

## 完成度结论

截至 2026-07-29，可以确认：

- **V3 唯一生产协议已经完成。** 生产 WebSocket 只接受 V3
  `EventEnvelope`；Handler、Emitter、前端 Registry/Adapter 已不再依赖 V2，
  兼容模块已删除，持久化数据已迁移并校验。
- **文字、固定音频、取消和真实工具主链路已有实机证据。** 这满足本次协议迁移
  对核心运行链的完成定义。
- **不能把它等同于整个陪伴产品已经 100% 验收完成。** 原实施计划中的真实麦克风、
  TTS/GSVI 故障降级、主动发言、工具审批闭环、Memory 重启读取、连续三次
  Electron 启停，尚未在本报告中留下完整证据。
- **有一项计划与实现不完全一致。** 计划要求最多 1024 项的 `eventId`
  响应缓存并在可用时重放同步响应；当前实现是最多 2048 项的连接内去重缓存，
  重复事件作为幂等 no-op，不提供响应重放。这不阻断已验收主链，但应单独决定
  是修改计划口径，还是后续补齐响应重放语义。

因此，准确结论是：**V3 协议全迁移完成；V3 产品级完整验收尚未全部完成。**

## 架构变化

迁移前：

```text
V3 Envelope → V2 InboundMessage → V2 Handler/Pipeline
→ V2 OutboundMessage → V3 包装 → 前端恢复 V2 payload
```

迁移后：

```text
V3 EventEnvelope → typed RuntimeEvent → V3 RuntimeEventHandler
→ CharacterTurn → typed DomainEvent → Session Writer
→ frontend V3 registry → RuntimeEventAdapter
```

## 主要迁移矩阵

| 旧类型/事件 | V3 替代 | 最终处理 |
|---|---|---|
| `text_input` | `user.text` | flat input 删除 |
| `audio_input`, `audio_end` | `user.audio.started/chunk/completed` | flat input 和 Bridge mic buffer 删除 |
| `interrupt` | `turn.cancelled` / `user.audio.cancelled` | typed cancellation |
| `command` | `management.requested` | typed result/failed |
| `assistant_message` | `assistant.text.completed` | V2 class/helper 删除 |
| `character_update` | `character.intent` | Avatar flat update 删除 |
| `tts_start/audio/end` | `tts.started/audio/completed` | V2 classes/helpers 删除 |
| `runtime_status` | `runtime.status/ready/degraded` | V2 dispatch 删除 |
| `avatar_*` flat messages | `character.*` | transport-neutral Avatar domain events |
| `tone`, `gesture` segment fields | `emotion`, `behavior` | 运行时 fallback 删除，持久化数据一次性升级 |
| `character/v2`, `tone_words` | `character/v3`, `emotion_words` | tracked character config 升级 |

## 删除的生产模块

- `app/transport/v2_adapter.py`
- `app/transport/protocol.py`
- `app/transport/v3_emitter.py`
- `contracts/v3/compat.py`
- `contracts/v3/payloads.py`
- `frontend/src/runtime/protocol.ts`
- `frontend/src/runtime/compat.ts`
- `app/avatar/protocol.py`
- `app/memory/history_migration.py`

## 数据迁移

2026-07-29 实际执行结果：

- SQLite 记录升级：583
- 旧结构化键迁移：550
- 校验错误：0
- `memory.db` integrity check：`ok`
- `turns.db` integrity check：`ok`
- 二次 dry-run：0 条待迁移
- 历史 JSON：57 份源文件已有逐字节一致的 `v2-archive`
- 备份清单：`data/backups/v3-protocol/20260729T125940.468944Z/manifest.json`

数据库、历史和备份是用户运行时数据，不进入 Git。

## 同名但不属于旧协议的内容

以下内容不是 V2 wire/business compatibility，不做错误替换：

- `GPT-SoVITS v2Pro` 的产品名、目录和 API 文件名。
- Live2D MotionManager 的 `gesture` 动作分类；它表示一次性模型动作，不是
  LLM segment 的旧 `gesture` 字段。
- 自然语言中的 “tone”，例如人格写作风格说明。
- 一次性迁移脚本和迁移报告中的历史字段名。

架构守卫会扫描 Bridge、Runtime、Transport、V3 contracts 和前端 runtime，
禁止重新引入 V2 类型、flat wire event 或旧业务字段读取。

## 阶段提交

- V3-1 Schema 与 Registry：`c9dec90`
- V3-2 后端入站：`f12ca83`
- V3-3 后端出站：`18c058c`
- V3-4 前端消费：`8e2c92f`
- V3-5 数据迁移：`17c43b2`
- 工具名冲突修复：`211ca03`
- Electron 启动轮询回归测试修正：`48d9bce`
- Electron 启动页恢复与 Bridge 阈值修复：`2595b15`
- V3-6 删除 V2 与架构守卫：`0df7cda`

## 真实运行验收

2026-07-29 从 `soulctl.cmd electron` 实际启动：

- Electron 主窗口显示，WebSocket 显示已连接，Live2D 模型实际渲染。
- LLM、Memory、Bridge、ASR、GSVI、TTS 均创建真实进程并达到可用状态。
- 文本回合返回“V3全链成功”，事件顺序为
  `session.opened → turn.started → assistant.text.started/completed →
  tts.started/audio/completed → character.intent → turn.completed`。
- 文本回合的 `sessionId` 全程一致，所有 turn 事件使用同一 `turnId`，
  出站 `sequence` 从 1 到 9 连续递增；TTS 音频为 250,940 字节 Base64。
- 固定音频独立 ASR 识别为“你好，这是语音识别测试。”；集成语音回合收到
  `asr.started/result`，随后完成 LLM、TTS、Character 与 turn，出站
  `sequence` 从 1 到 11 连续递增，TTS 音频为 622,992 字节 Base64。
- 运行中的旧回合取消后收到 `tts.cancelled` 和 `turn.cancelled`；
  旧 turn 事件返回 `stale_turn`，取消后没有旧 Assistant、TTS 或 Character
  事件泄漏，新回合正常完成。
- `get_current_time` 真实工具调用收到 `tool.started → tool.result`，
  不再出现 `Tool names must be unique`。
- 退出后精确检查项目 Electron、Lifecycle Supervisor 和六个服务进程，
  未发现残留。

自动验证：

- Python：372 passed，30 skipped。
- 前端：42 passed。
- TypeScript：`tsc --noEmit` 通过。
- Vite production build 通过。

仍需补充的真实验收证据：

1. 真实麦克风采集，而不只是固定音频输入。
2. TTS 与 GSVI 故障时，文字与 Character 链路继续可用。
3. 主动发言与普通用户回合共用同一 V3 事件链。
4. 需要审批的工具完成 `requested → approval → result/failed` 闭环。
5. Memory 保存后重启服务，并验证读取一致。
6. 连续三次 Electron 启动、交互和退出均无残留进程。
