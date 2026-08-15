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

## 验证纪律（必须遵守）

1. 任何结论/断言必须有 `file:line` 证据；没读过该文件就不得下结论，禁止凭印象发言。
2. 报告与反驳不得夸大证据；被问及时必须给出与先前核实一致的结论，发现前后矛盾立即认账修正。
3. 修改任何文件前，先列出改动面清单（文件/行/连带调用方/连带测试）等确认后再动手。
4. 动代码前跑相关测试，动完再跑一遍；完成声明不算验收证据。
5. 拿不准的、有歧义的，先问，不猜不赌；涉及删除/迁移先扫全仓库引用。

