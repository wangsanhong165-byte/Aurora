# Lifecycle Architecture

服务清单按 `manifest < 用户覆盖 < 环境变量 < CLI` 解析；当前正式入口使用 manifest 和环境变量，程序化调用可传入用户/CLI overrides。解析结果执行重复端口、缺失依赖和依赖环验证。

Core 按拓扑顺序启动，逐项等待 readiness 并执行声明式 warmup；任一步失败即逆序清理本次已启动服务。注册记录包含 PID、创建时间、可执行文件、完整命令和端口。终止前重新读取实际身份，PID 被复用或身份不一致时拒绝终止。未知端口占用返回 `blocked_external`。

Electron 只维护 Python supervisor 的 stdin/stdout 请求；服务事实和进程规则不进入 Node。Supervisor 在 stdin EOF 时执行清理。Python CLI、`run.py` 和 Electron 共享同一 Core。

## 测试矩阵与验证

- manifest 覆盖、拓扑顺序和环检测。
- PID 创建时间变化时拒绝身份匹配。
- Electron 适配器静态确认无服务清单、netstat 或 taskkill。
- CLI status 动态确认未知端口只报告 `blocked_external`，不终止监听者。
- 真实模型全量启动属于长时 GPU 验收，应在目标机器空闲且模型资产完整时运行；自动测试使用短生命周期替身和平台适配器。

## 生产入口

- 交互 Runtime：`python run.py`
- Web 一键启动：`start_web.bat`，统一委托 `scripts/launcher.py web`
- 后端：`python scripts/lifecycle.py start --mode backend`
- Electron 一键启动：`start_electron.bat`，统一委托 `scripts/launcher.py electron`

启动器按 `MAIN_PYTHON`、未提交的 `config/runtime.local.json`、已知项目 Conda 环境、当前解释器依次选择 Python，执行依赖与资产预检，并在启动前构建前端。可用 `python scripts/launcher.py doctor` 单独诊断环境；本机配置模板见 `config/runtime.local.example.json`。
