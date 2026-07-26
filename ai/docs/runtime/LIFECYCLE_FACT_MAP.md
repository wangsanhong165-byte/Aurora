# Lifecycle Fact Map

## 迁移前

`run.py`、`scripts/lifecycle.py` 和 `electron/process-manager.cjs` 分别定义服务命令、GPU 启动顺序、探活、预热和关闭。Python CLI 把 PID 文件或端口当作所有权依据；Electron 会先杀死端口监听者。批处理入口另有 PID 清理逻辑。

## 唯一所有者

| 事实 | 最终所有者 |
| --- | --- |
| 服务、命令、端口、依赖、profile、readiness、warmup | `config/services.json` |
| 配置解析与拓扑验证 | `ServiceManifest` |
| 启动、回滚、停止、重启 | `LifecycleOrchestrator` |
| PID 与进程身份 | `ProcessRegistry` / `PlatformProcessAdapter` |
| HTTP/端口 readiness | `HealthProbe` |
| Python 命令行 | `scripts/lifecycle.py` |
| Electron 适配 | `electron/process-manager.cjs` |

## 删除清单与引用清零

- 删除三个入口中的独立服务数组和端口清单。
- 删除 Electron 按端口执行 netstat/taskkill 的路径。
- 删除 Python 在没有可信注册记录时按端口停止进程的 fallback。
- 删除批处理中的 PID、端口和进程清理规则。
- `run.py` 不再自行构造服务命令、轮询健康或管理服务 PID。
