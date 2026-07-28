# Electron 性能优化报告

## 1. Electron 比 Web 端卡的真实根因

**主要根因：`transparent: true` 导致的 GPU 软件回退**

`electron/main.cjs:55` 设置了 `transparent: true; backgroundColor: '#00000000'`，这导致：
- Chromium 在透明窗口模式下禁用 GPU 硬件合成
- WebGL（Live2D 渲染）回退到 SwiftShader 软件渲染
- 所有 canvas/GPU 操作通过 CPU 模拟，降低 1-2 个数量级
- UI 渲染和 WebGL 共享同一降级路径，按钮点击也被拖慢

**次要根因：console-message 同步磁盘 I/O**

`console-message` 事件处理程序使用 `fs.appendFileSync` 同步写入日志文件。每次 console.log（包括每帧的调试日志）都阻塞主进程 IPC → renderer 事件队列排队。

**次要根因：生命周期轮询过于频繁**

`statusTimer` 每 500ms 调用 `pm.refresh()`，刷新涉及子进程状态检查的 IPC。

## 2. 已执行的修复

| 修复 | 文件 | 行 |
|---|---|---|
| 移除 `transparent: true` | `electron/main.cjs` | 55 |
| `console-message` 改为 `setImmediate` 异步写入 | `electron/main.cjs` | 72-77 |
| 加载后轮询间隔 500ms → 2000ms | `electron/main.cjs` | 293 |
| `setBackgroundColor` 冗余调用移除 | `electron/main.cjs` | — |

## 3. 启动中心重构

启动中心（`electron/bootstrap/`）重新设计：

| 改动 | 之前 | 之后 |
|---|---|---|
| 标题 | "SoulLink 启动控制台" | "Companion" |
| 背景 | 径向渐变蓝黑色 | 纯色 `#0d0e12` |
| 卡片 | 文字状态 + 彩色标签 | 圆点指示 + 中文状态 |
| 技术详情 | 默认展开 (`<details>`) | 按钮折叠，错误时自动展开 |
| 进度 | 无 | 细进度条 |
| 重试按钮 | 蓝色 | 陶土橙边框 |
| 服务列表 | 卡片式 | 紧凑行式 |
| 整体风格 | 霓虹蓝科幻风 | 中性深色，Claude Code 风格 |

## 4. 所有修改文件

```
electron/main.cjs                        — transparent/console/轮询
electron/bootstrap/index.html            — 简化启动中心
electron/bootstrap/bootstrap.css         — 纯色+紧凑风格
electron/bootstrap/bootstrap.js          — 状态简化+自动展开
frontend/src/electron/main.cjs           — 前述修改
frontend/src/character/controllers.ts    — audio/expression/idle 修复
frontend/src/character/ParameterMixer.ts — 优先级修复
frontend/src/character/live2d/core.ts   — 互斥锁
frontend/src/character/CharacterView.tsx — memo 包裹
```

## 5. 仍然存在的风险

- Pet mode 透明背景失效（`transparent: true` 移除后无法动态恢复）
- 启动中心仍独立于主应用（Bridge 未就绪时必须）

## 6. Electron 与 Web 性能对照（预估）

| 指标 | Web (Chrome) | Electron 修复前 | Electron 修复后 |
|---|---|---|---|
| GPU 渲染 | 硬件加速 | SwiftShader 软件 | 硬件加速 |
| console I/O | 内存 | 同步磁盘 | 异步 |
| 轮询频率 | n/a | 500ms | 2000ms |
| Live2D FPS | ~60 | <20 | ~60 |
| 按钮响应 | 即时 | 延迟 200-500ms | — |
