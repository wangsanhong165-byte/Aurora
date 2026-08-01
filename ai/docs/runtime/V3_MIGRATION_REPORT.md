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

## Live2D 完成边界

截至 2026-07-30，对照 SoulLink Emotion SDK
`932a61c811dbe9432bf8e824a93acb96feb782cc` 与 AIRI
`a42e3ae0b51000c552d7cd19e6c20fa10918a614` 的实际源码，Live2D 表现运行时升级已完成：

- 音频事件保留 `turnId/sequence`，播放队列按轮次拥有音频，过期片段不会污染新回复；
  停止与销毁生命周期已分离。
- 模型能力、参数范围、保护通道、嘴型范围和表现风格集中在
  `AvatarCapabilityProfile`，未知或不支持的参数会在写入前过滤和钳制。
- 原生动作与程序化动作统一进入带 owner、channel、turnId、优先级和 TTL 的
  `MotionArbiter`，模型切换、打断和 detach 会释放相应所有权。
- motion3 的 `Parameter` 和 `PartOpacity` 曲线都进入贡献链；Pose、Expression
  与 Native Motion 的透明度写入由 `ParameterMixer` 统一仲裁和恢复。
- VAD 手势、微动作、等待动作和语音重音支持动作族、重复规避、平滑过渡；
  LipSync 加入噪声门、attack/release、峰值强调与嘴型保护。
- `character.intent.motionPlan` 已加入 V3 强类型协议；后端只保留十种安全动作
  原语、有限时长/步骤/强度，前端再编译为逻辑参数轨道，拒绝 Param/Cubism
  字段、任意关键帧和渲染器细节。
- 设置页已集成按模型保存的自然增强/兼容模式、动作强度、快速表情/触摸试演、
  自动恢复的参数校准实验室、真实口型诊断，以及动作创建、编辑、试演和导入导出。
- Ariu（113 参数、356 drawable）与 Hiyori（70 参数、134 drawable）已在
  生产构建页面完成真实模型加载、切换和安全动作试演；Ariu 已增加模型专属取景，
  避免原始 Cubism 画布偏心造成主体裁切。最终控制台 0 错误、0 警告；
  严格画像检查、前端测试、类型检查与生产构建均纳入验收。
- 真实浏览器 `AudioContext` 诊断已覆盖播放、分析、口型驱动、中断与闭嘴：
  Hiyori 音量峰值 0.357、开口峰值 0.750、结束嘴型 0.000。外部 TTS 的
  V3 音频输出证据见本报告“真实运行验收”。

因此，Live2D 的准确状态是：**本轮定义的核心表现运行时、PartOpacity 保真、
安全动作编排、动作创作链和真实浏览器音频验收均已完成。** 逐模型的美术表现
仍属于持续调校，而不是协议或控制链缺口。
后续扩展继续保持 `ParameterMixer → Live2DModelAdapter` 为唯一 Cubism 参数写入链，
不引入 V4、第二套 EventBus 或第二套状态机。

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
