# Runtime V3 生产路径清场设计

## 目标

V3 Runtime 只保留一条生产交互链路：

`/client-ws → WebSocketSession → RuntimeEventHandler → CharacterRuntime.handle_turn()`

V2 Transport 是这条链路的正式协议，不因 Runtime 升级到 V3 而改名或删除。

## 删除边界

- 删除 `/ws` 旧 Live2D relay WebSocket。
- 删除 `/v2/ws` 重复 Runtime WebSocket，`/client-ws` 直接承载正式 session。
- 删除测试中的 `CompanionRuntime`、`dispatch(Event)` 和 replay legacy adapter。
- 删除 Runtime/Bridge 中暗示生产双路径仍存在的注释。
- 将 session 初始化的 `protocol_version` 从错误的 `1.0` 统一为 `2.0`。

## 保留边界

- 保留 Memory 历史导入、旧 facts 回填和 nullable 迁移字段；它们只读取旧数据，不形成运行时双写。
- 保留现有 Tool Provider；其名称虽含 legacy，但仍是当前工具能力的唯一适配器。
- 保留前端 `legacy` 表现调试模式；它只调整 Live2D 参数策略，不绕过 ParameterMixer。
- 保留 HTTP Live2D 配置接口，前提是它们不直接写 Cubism 参数。

## 验收

- FastAPI 只注册 `/client-ws` 一个 WebSocket 路由。
- session 初始化明确发送 `protocol_version: "2.0"`。
- `app/` 与生产测试中不存在 `CompanionRuntime` 或 Runtime `dispatch()` 兼容入口。
- 文本、语音和 Initiative 测试均直接调用 `handle_turn()`。
- 全量 pytest、前端 typecheck 和 build 通过。
