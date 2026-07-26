# SoulLink 源码启动架构

`soulctl.cmd` 是 Windows 源码环境唯一正式入口。Node 控制器只负责环境发现、前端构建指纹、命令转发和终端展示；服务依赖、readiness、预热、回滚、进程身份和停止全部由 Python Lifecycle Supervisor 决定。

Supervisor 按工作区驻留，通过带当前用户控制令牌的本地 Named Pipe 提供命令和状态快照。Electron 内置 Bootstrap 页面不依赖 React、Vite、Bridge 或 `dist`，动态展示 manifest 声明的能力，并在达到 `TEXT_READY` 后进入角色界面。

```powershell
soulctl.cmd electron
soulctl.cmd electron --hot
soulctl.cmd web
soulctl.cmd start
soulctl.cmd status
soulctl.cmd restart
soulctl.cmd stop
soulctl.cmd doctor
soulctl.cmd diagnostics
```

`start` 创建后台 launch，需显式 `stop`；Electron 是自身 launch 的 owner，真正退出时清理。未知端口占用只报告为 `blocked_external`，不会终止外部进程。

旧的 `start_web.bat`、`start_electron.bat`、`scripts/launch.cmd`、`scripts/launcher.py` 和独立生命周期 CLI 已删除，不存在新旧双路径。
