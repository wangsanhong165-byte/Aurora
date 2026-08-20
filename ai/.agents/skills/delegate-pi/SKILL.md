---
name: delegate-pi
description: 将边界明确、可验证且经用户批准的机械执行任务同步委派给 Pi CLI，并固定使用 OpenCode Go 的 DeepSeek V4 Flash、thinking=max。规划、架构、人格系统核心、Review、最终测试、安全敏感和视觉任务必须由主 Agent 自己完成。
---

# 委派给 Pi / DeepSeek V4 Flash

> 质量优先：`thinking` 固定为 `max`，禁止降档；省 token 不得降低推理强度。默认不委派，只有主 Agent 向用户列明任务边界并获用户同意后，才可调用本流程。

这是单执行器、单模型、单推理档位的轻量委派流程：

```text
主 Agent -> Pi CLI -> OpenCode Go -> DeepSeek V4 Flash
```

不得接入其他 CLI，不得配置其他模型，不得自动选择模型，不得 fallback，不得降低 thinking。

## 路由原则

凡是需要判断方向的工作，由主 Agent 完成。边界明确、结果可测试、经用户批准的机械执行工作，可以交给 Pi。

### 主 Agent 必须自己完成

- 需求理解、澄清和全项目调查
- 架构、协议、数据模型和多方案取舍
- 人格系统核心与认知模块设计实现
- 工作拆分和高风险重构
- 身份验证、权限、支付、密钥和生产数据修改
- 破坏性操作
- 最终代码 Review、最终测试和最终验收
- 生图和视觉生成
- Pi 失败后的修复决策

### 仅可委派（仍需用户批准当前任务边界）

- 边界明确的普通功能实现或局部 Bug 修复
- 单元测试、类型、lint 和文档同步
- 重复性修改和明确范围内的重构
- 有复现步骤的普通调试
- 指定模块的代码调查

### 禁止委派

- 需求模糊或无法定义验收标准的工作
- 需要架构选择、安全判断或生产数据操作的工作
- 人格系统核心、认知模块、高风险重构
- 修改范围未知或跨大量模块的工作
- 最终 Review 或对 Pi 自己产出的验收
- 与其他执行 Agent 同时修改同一批文件的工作

## 执行流程

1. 主 Agent 先调查项目，确认真实文件、约束和验证命令。
2. 默认不委派；只有用户批准当前具体任务的边界后才继续。
3. 在 `.agent-runs/tasks/<task-id>.json` 写入单一目标、最小 `allowed_paths`、可验证验收条件和真实验证命令。
4. 工作区脏时默认不委派；确需基于现有修改时，由主 Agent 明确使用 `--allow-dirty`。
5. 调用：

   ```powershell
   python tools/delegate_pi.py run --task .agent-runs/tasks/<task-id>.json
   ```

6. 同步等待 Pi 完成，读取 `.agent-runs/results/<task-id>.json` 和对应 JSONL 输出。
7. 主 Agent 检查 Git diff，逐个 Review 修改文件并检查越界。
8. 主 Agent 独立运行验证命令和项目测试。
9. 不合格结果由主 Agent 修复或拒绝，不能再次盲目交给 Pi。
10. 主 Agent 向用户汇报经过独立验证的最终结果。

所有委派任务固定使用 `max`；模型仍必须是 DeepSeek V4 Flash。没有降低推理强度的选项，省 token 不得作为降档理由。

## 质量责任

DeepSeek Flash 的“已完成”“测试通过”“没有风险”等陈述均不可信，除非主 Agent 已经独立验证。

子 Agent 输出只是候选实现，不是最终结论。

最终质量责任始终属于主 Agent。
