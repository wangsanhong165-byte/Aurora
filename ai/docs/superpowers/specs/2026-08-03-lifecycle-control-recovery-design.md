# 生命周期控制面恢复设计

## 目标

在不新增第二套进程管理器、不改变现有 Orchestrator 所有权规则的前提下，改善 `soulctl` 面对旧 Supervisor、失效控制记录和不可访问控制管道时的处理方式。

目标是让现有系统遵循：

```text
优先复用现有 Supervisor
  -> 校验控制记录与进程身份
  -> 区分已失效、暂不可访问、可恢复三种状态
  -> 只有显式恢复时才回收匹配的 Supervisor
  -> 重新连接并等待服务 readiness
```

## 当前架构与问题边界

- `ControlServer` 为每个工作区创建一个稳定的本地控制端点，并把 endpoint、token、PID 写入 `data/runtime/lifecycle-control.json`。
- `soulctl` 通过该记录连接 Supervisor；记录存在但 `status` 失败时，如果 PID 仍存活，目前会直接报错并要求用户关闭旧实例或回到同一 Windows 会话。
- `LifecycleOrchestrator` 已经按 `profile`、依赖和 readiness 管理服务。
- `ProcessRegistry` 通过 PID、创建时间、可执行文件、命令行和端口匹配进程，并保存 owner；未知端口进程不会被 Orchestrator 回收。
- Windows `Job Object` 已经用于回收 Orchestrator 自己启动的服务树。

因此，本设计只处理 Supervisor 控制面的复用与恢复，不重新设计服务所有权，也不让调试进程自动进入生产服务树。

## 关键决策

### 1. 默认复用，不创建第二个 Supervisor

`soulctl` 的默认行为保持单工作区单 Supervisor：

- 没有控制记录：启动 Supervisor 并等待控制端点可用。
- 控制记录有效且 `status` 成功：直接复用现有 Supervisor。
- 控制记录指向的 PID 已不存在：视为陈旧记录，安全清理后启动新的 Supervisor。
- PID 存活但端点不可访问：不自动强杀、不启动第二个 Supervisor，返回可诊断的控制面错误。

### 2. 恢复必须是显式动作

增加一个面向已有 `soulctl` 入口的显式恢复流程，而不是新增独立管理器。恢复前必须验证：

- PID 仍与控制记录一致；
- 可执行文件是当前选择的 Python；
- 命令行确实是本工作区的 `app.lifecycle.supervisor --serve`；
- 进程身份信息能够可靠读取。

任一校验失败，都只报告“无法安全确认归属”，不终止该进程。校验通过后才允许回收匹配的 Supervisor、清理控制记录并重新建立端点。

### 3. 不自动接管调试进程

Codex 调试遵循现有架构：

- 查询、日志、诊断和普通测试优先复用当前 Supervisor；
- 直接启动且占用服务端口的调试进程继续被标记为 `external/unverified`；
- 生命周期管理器不因端口冲突终止调试进程；
- Codex 不直接启动第二个 `app.lifecycle.supervisor --serve`。

### 4. readiness 仍由现有 Orchestrator 负责

恢复控制面后，服务启动、依赖排序、GSVI readiness、能力等级和 Job Object 仍走现有 Orchestrator。控制面恢复成功不等于模型服务已就绪；调用方必须继续等待并检查 `status` 的服务状态。

## 数据流

```text
soulctl
  -> 读取 lifecycle-control.json
  -> 尝试 status
  -> 成功：复用现有 Supervisor
  -> PID 消失：清理陈旧记录并启动
  -> PID 存活但管道失败：返回控制面诊断
  -> 显式 recover 且身份匹配：回收 Supervisor、重建端点
  -> 调用现有 start/profile
  -> 等待 Orchestrator readiness
```

## 错误处理与用户可见结果

错误信息需要区分：

- `control_record_missing`：没有控制记录，可以正常启动；
- `control_record_stale`：记录中的 PID 已退出，可以安全重建；
- `control_endpoint_unavailable`：PID 仍存活但端点不可访问，提示可能是 Windows 会话或权限不一致；
- `control_owner_unverified`：无法确认该 PID 属于本工作区，禁止自动回收；
- `control_recovered`：已显式恢复并重新建立控制端点。

这些状态不改变前端现有服务能力模型；它们首先用于 `soulctl` 输出、生命周期日志和诊断文件。

## 验收标准

- 已有健康 Supervisor 被 `soulctl` 复用，不产生第二个 Supervisor。
- 陈旧控制记录不会阻塞新启动。
- PID 存活但管道不可访问时，默认不会强杀或覆盖旧实例。
- 显式恢复只会处理经过命令行、可执行文件和创建时间校验的 Supervisor。
- 外部调试进程占用端口时，Orchestrator 仍拒绝接管且不终止它。
- 恢复后仍通过现有 profile、依赖、readiness 和 Job Object 链路启动服务。
- 增加控制面状态测试、恢复身份校验测试和外部进程保护测试。
- 不修改提示词、LLM、GPU、GSVI、TTS、ASR、Live2D 或现有服务所有权逻辑。

## 非目标

- 不新增独立调试模式或第二套端口体系。
- 不把所有端口占用都当作可自动清理的孤儿进程。
- 不用“9528 可访问”代替完整服务 readiness。
- 不通过恢复流程绕过模型服务自身的安全规则或进程权限。
