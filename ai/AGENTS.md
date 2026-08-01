# 项目 Agent 规则

## 单模型委派

本项目允许 Codex 使用 `.agents/skills/delegate-pi/SKILL.md`，把边界明确、可验证的普通执行任务同步委派给 Pi CLI。

固定调用链：

```text
Codex -> Pi CLI -> OpenCode Go -> DeepSeek V4 Flash
```

- 唯一 provider：`opencode-go`
- 唯一模型：`deepseek-v4-flash`
- 禁止其他执行 CLI、其他模型、自动模型选择和 fallback
- 不得为了节省 Codex 额度而强制委派

Codex 负责需求、调查、规划、架构、任务拆分、高风险修改、安全敏感修改、最终 Review、最终测试、最终验收和视觉生成。Pi 只负责已经拆清边界的普通实现、局部修复、测试补充、lint、类型、文档同步、重复性修改和指定模块调查。

调用 Pi 后，Codex 必须检查完整输出与 Git diff，逐文件 Review，并独立运行测试。Pi 的完成声明不是验收证据。

临时禁用委派：把 `.agent-router/config.json` 中的 `enabled` 改为 `false`。
