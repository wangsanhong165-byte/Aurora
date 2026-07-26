# Runtime V3 生产路径清场实施计划

> **面向 AI 代理的工作者：** 使用 executing-plans 在当前任务中逐项实施。

**目标：** 删除 V3 Runtime 周围的生产双路径，同时保留 V2 Transport、历史迁移和非 Runtime 的兼容能力。

**架构：** `/client-ws` 是唯一 WebSocket 入口，直接构造 `WebSocketSession` 与 `RuntimeEventHandler`。所有交互继续进入 `CharacterRuntime.handle_turn()`；协议初始化统一为 2.0。

**技术栈：** FastAPI、Python dataclasses、pytest、React/TypeScript、Vite。

---

### 任务 1：锁定唯一 WebSocket 和协议版本

**文件：**
- 修改：`tests/test_transport_emitter_v3.py`
- 修改：`app/bridge/server.py`
- 修改：`app/transport/session.py`

- [ ] 增加测试，断言 WebSocket 路由集合只有 `/client-ws`。
- [ ] 增加 session 初始化测试，断言 `protocol_version == "2.0"`。
- [ ] 运行定向测试并确认因旧路由和 1.0 标识失败。
- [ ] 删除 `/ws` 和 `/v2/ws`，让 `/client-ws` 直接运行正式 session。
- [ ] 修改协议标识为 2.0，运行定向测试确认通过。

### 任务 2：删除 Runtime 测试兼容壳

**文件：**
- 修改：`tests/test_runtime_pipeline.py`
- 删除：`tests/runtime_v3_adapter.py`
- 创建：`tests/turn_input_fixtures.py`
- 修改：`tests/test_replay_quality_v3.py`

- [ ] 增加静态边界测试，禁止生产/核心测试出现 `class CompanionRuntime` 和 `dispatch(Event)`。
- [ ] 运行测试并确认被现有兼容壳触发。
- [ ] 将测试输入直接转换为 `TurnInput`，调用 `CharacterRuntime.handle_turn()`。
- [ ] 删除不再需要的 replay adapter 文件。
- [ ] 运行 Runtime 和 replay 测试确认通过。

### 任务 3：清理误导性生产注释

**文件：**
- 修改：`app/runtime/management.py`
- 修改：`app/transport/management.py`
- 修改：`app/runtime/runtime.py`
- 修改：`ARCHITECTURE.md`

- [ ] 删除暗示 legacy Bridge/dispatch 仍是生产入口的注释。
- [ ] 保留 Memory migration 和 Tool Provider 的兼容说明。
- [ ] 运行静态边界测试，确认不存在生产 Runtime 双路径表述。

### 任务 4：完整验证

**文件：**
- 验证：全部相关文件

- [ ] 运行 `python -m pytest -q`。
- [ ] 运行 `npm.cmd run typecheck`。
- [ ] 运行 `npm.cmd run build`。
- [ ] 运行源码扫描，确认唯一 WebSocket、无 Runtime 兼容壳且迁移边界仍在。
- [ ] 检查 Git diff，确认未包含运行数据。
