# 角色提示词配置与请求记录设计

## 目标

为当前角色提供一个可从左侧功能栏打开的“提示词”控制台。用户可以查看、替换、关闭或恢复各 system 上下文来源，同时在独立的只读页面核对最近一次真实 LLM 请求。所有可编辑内容按角色独立保存。

## 数据流

```text
PromptPanel
  -> requestCommand("get_prompt_config" / "set_prompt_config")
  -> ManagementHandler
  -> RuntimeManager
  -> data/prompts/<character_id>.json  (来源策略)
  -> data/prompts/<character_id>.md    (附加提示词)
  -> DefaultPlanner
  -> PromptCompiler / DecisionStep
  -> ContextBudget
  -> LLM.generate
```

## 关键决策

- 采用独立配置文件，不直接改写角色包内的 `character.json`，避免覆盖角色资源。
- 以显式角色 ID 为隔离键，角色切换后读取另一份内容，保存不会因切换竞态写错角色。
- `language`、`persona`、`memory_summary`、`relevant_memory`、`emotion`、`character_state` 支持使用默认、自定义替换、关闭三种模式。
- `output_protocol` 维持结构化回复、动作和语音链路，必须可查看但保持只读。
- 附加提示词放在角色基础设定之后、记忆和对话历史之前；空内容表示不追加。
- 不把字段塞进前端 `AppSettings`；UI 设置持久化与 LLM 运行时上下文是两条不同职责链。
- 面板沿用现有 `DrawerPanel`、Lucide 图标、蓝灰 token、焦点环和抽屉宽度约束。
- 只提供合法的项目/角色自定义提示词入口，不添加绕过模型安全策略的逻辑。

## 提示词配置与请求记录

面板明确拆成两个标签：

- **提示词配置（可编辑）：** 只展示 system 来源，不展示用户输入。来源策略按角色保存；切换角色后立即加载对应配置，未保存草稿按角色暂存。
- **请求记录（只读）：** `DecisionStep` 在每次真正调用 LLM 前记录经过 `ContextBudget` 裁剪后的消息列表；运行时保存最近一次快照，包含 system 上下文、本轮用户输入、历史回复与工具结果。

配置通过 `get_prompt_config` / `set_prompt_config` 管理动作读写；请求审计通过 `get_prompt_view` 返回最近一次真实请求和上下文预算。管理动作都接受显式 `character_id`。尚未发生该角色的 LLM 请求时，请求页显示无记录，不复用其他角色的旧快照。

## 验收标准

- 左侧导航显示“提示词”，激活后默认打开配置页。
- 保存和重新打开后来源模式、替换内容和附加内容一致。
- `monika` 与其他角色的配置、附加内容和未保存草稿互不覆盖。
- 关闭来源会从下一轮实际 LLM 请求中移除；替换来源会完全替代默认内容；恢复默认后重新生成默认内容。
- 配置页不显示用户输入；请求记录页明确把用户输入标记为“本轮输入”。
- 输出协议可查看且只读；其他声明为可编辑的 system 来源支持默认、替换、关闭。
- 空附加内容不会产生额外 system 消息。
- 切换角色后立即加载对应配置，旧角色快照不会泄漏到新角色页面。
- Python 定向测试、前端类型检查、构建和全量测试通过。
