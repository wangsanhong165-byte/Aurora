# Pi / DeepSeek V4 Flash 委派

## 用途

这套委派层用于把用户批准、边界明确的机械执行任务交给 DeepSeek V4 Flash。主 Agent（我，不是 Codex）始终负责方向判断和最终质量，Pi 只执行已经拆清边界、可自动验证的任务；质量优先于省 token。

```text
主 Agent -> Pi CLI -> OpenCode Go API -> DeepSeek V4 Flash
```

系统固定使用 `opencode-go/deepseek-v4-flash`，不支持候选模型、自动路由、并行 Agent 或 fallback。

## 初始化与登录

安装 Pi：

```powershell
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
pi --version
```

登录 OpenCode Go：

```powershell
pi
```

进入 Pi 后运行 `/login`，选择 `OpenCode Go`，在 Pi 界面粘贴 API Key。不要把 Key 写进项目文件、任务 JSON、命令参数或日志。

登录后检查：

```powershell
pi --list-models opencode-go
python tools/delegate_pi.py init
python tools/delegate_pi.py check
```

`check` 必须看到 provider `opencode-go` 和模型 `deepseek-v4-flash` 才会通过。

Windows 兼容说明：Pi 的同步非交互模式使用完整参数 `--print`。委派器不会使用短参数 `-p`，并会把仅含任务文件路径的短提示规范化为单行，避免 `pi.cmd` 在首个换行处截断参数。完整任务内容始终保存在任务 JSON 中。

## 主 Agent 何时委派

适合委派：局部功能、普通 Bug、单元测试、类型和 lint 修复、文档同步、重复性修改、明确范围内重构、指定模块调查。

不适合委派：模糊需求、架构选择、高风险重构、权限支付密钥、生产数据、破坏性操作、最终 Review、最终验收和视觉生成。

完整路由规则见 `.agents/skills/delegate-pi/SKILL.md`。

## 手动创建任务

任务文件保存在 `.agent-runs/tasks/`：

```json
{
  "task_id": "example-task",
  "objective": "为指定解析函数补充空输入回归测试并修复该问题。",
  "allowed_paths": ["app/parser.py", "tests/test_parser.py"],
  "acceptance_criteria": ["空输入返回明确错误", "现有测试不被弱化"],
  "validation_commands": ["pytest -q tests/test_parser.py"],
  "constraints": ["不得修改其他模块", "不得执行 Git 写操作"]
}
```

任务不得包含 Key、Token、Cookie 或密码。`allowed_paths` 应尽量小，验证命令必须来自真实项目调查。

## 调用

```powershell
python tools/delegate_pi.py init

python tools/delegate_pi.py check

python tools/delegate_pi.py run `
  --task .agent-runs/tasks/example-task.json

# thinking 固定 max，通常不需要传参；--thinking 仅接受 max
python tools/delegate_pi.py run `
  --task .agent-runs/tasks/example-task.json `
  --thinking max

python tools/delegate_pi.py stats
```

工作区存在未提交修改时默认拒绝。主 Agent 明确确认任务必须基于当前修改时，才可增加 `--allow-dirty`。

## 日志

- 调用摘要：`.agent-runs/logs/delegations.jsonl`
- 结构化结果：`.agent-runs/results/<task-id>.json`
- Pi 原始 JSONL：`.agent-runs/results/<task-id>.pi.jsonl`

日志只保存 Pi 实际返回的 token、缓存和费用字段；缺少字段时不会编造。输出写入前会执行凭据脱敏。

## 常见错误

- `pi_not_found`：安装 Pi，或修复 PATH。
- `not_authenticated`：在 Pi 中 `/login`，选择 OpenCode Go。
- `model_not_found`：OpenCode Go 目录中没有精确的固定模型；不会切换 provider。
- `wrong_model`：配置被改成了其他 provider 或模型。
- `disabled`：配置中的 `enabled` 为 `false`。
- `invalid_task`：任务 JSON 缺字段、路径越界或疑似包含凭据。
- `dirty_worktree`：工作区不干净且未显式使用 `--allow-dirty`。
- `timeout`：Pi 超时；系统不会切换模型或自动重试。
- `cli_failure`：Pi 退出失败，查看对应结果文件。
- `invalid_json_output`：Pi 未返回合法 JSONL，原始脱敏输出已保留。
- `scope_violation`：Pi 修改了 `allowed_paths` 之外的文件；系统不会自动回滚。
- `validation_failed`：Pi 进程退出正常，但主 Agent 独立审查发现任务目标或验收标准未完成。

## 禁用与卸载

临时禁用：将 `.agent-router/config.json` 的 `enabled` 改为 `false`。

彻底卸载：删除 `.agent-router/`、`.agent-runs/`、`.agents/skills/delegate-pi/`、`tools/delegate_pi.py`、本文件，并从 `AGENTS.md` 与 `.gitignore` 删除对应段落。卸载项目路由不会删除 Pi 的用户级认证；如需清除凭据，请在 Pi 中使用 `/logout`。

## 安全限制

- API Key 仅由 Pi 的用户级认证管理。
- 委派器使用参数数组启动 Pi，不拼接 shell 命令。
- 不执行自动 commit、push、merge、reset、checkout 或 clean。
- 不自动回滚越界修改，避免破坏用户原有工作。
- Pi 结果必须由主 Agent 独立 Review 和测试。
