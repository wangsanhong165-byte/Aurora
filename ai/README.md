# Aurora / Monika Voice Companion

Windows 本地 AI 陪伴系统：接收文本或语音输入，经 Runtime V3、LLM、记忆和情绪/表现规划后，通过 TTS 与 Live2D 前端完成回应。

这份 README 只记录当前代码树中的可执行入口和架构边界。服务端口、启动配置和协议以 `config/services.json`、`app/`、`frontend/` 以及测试为准。

## 能力概览

- 文本与语音交互：ASR、LLM、TTS、VAD 和可选的屏幕/主动对话能力。
- Runtime V3：统一处理用户回合、主动回合、工具调用、记忆提交、语音和表现意图。
- Live2D：模型注册、角色独立配置、表情/参数/动作协调、口型和实时诊断。
- 本地记忆：SQLite 存储与 FTS5 检索；角色卡只引用模型和音色资源，不复制资源。
- 前端：React + Vite + Electron，浏览器和 Electron 共用 Bridge/WebSocket 协议。

## 环境要求

- Windows 10/11
- Python 3.10 或更高版本
- Node.js/npm（仅运行前端和 Electron 时需要）
- 麦克风仅在语音模式中需要
- GPU 不是硬性要求；ASR、TTS 和 GSVI 的实际运行方式由本机服务配置与可用硬件决定

项目默认使用本机配置的 Python/服务环境。密钥和机器相关覆盖项放在 `config/.env`、`config/runtime.local.json` 或环境变量中；这些文件被 Git 忽略，不要把密钥写入源码。

## 启动与停止

推荐使用 Windows 统一入口：

```powershell
# 先检查配置、解释器和服务端点
.\soulctl.cmd doctor

# 启动服务并打开 Electron 前端（生产构建模式）
.\soulctl.cmd electron

# 启动 Vite 热更新前端并打开 Electron
.\soulctl.cmd electron --hot

# 仅启动后端服务并打印 Bridge 地址
.\soulctl.cmd web

# 查看 / 重启 / 停止由 Supervisor 管理的服务
.\soulctl.cmd status
.\soulctl.cmd restart
.\soulctl.cmd stop
```

`electron` 会在需要时准备前端构建；`electron --hot` 用于开发时的 Vite 热更新。`web` 是后端/Bridge 启动入口，不等同于一个独立的前端开发服务器；需要调试前端时使用 `electron --hot` 或在 `frontend/` 执行 Vite 命令。

命令行入口仍然可用：

```powershell
# 语音模式
python run.py

# 纯文本模式
python run.py --text

# 单轮录音模式
python run.py --no-vad

# 启动后端 Web/Bridge 后进入运行流程
python run.py --web
```

停止时优先使用 `soulctl.cmd stop`，不要只关闭一个服务窗口。Supervisor 会按服务依赖关系执行停止并清理运行记录。

## 服务与端口

`config/services.json` 是已提交的服务清单和生命周期配置。下表是首选端口；首选端口被占用时，Supervisor 会依次尝试配置的备用端口，必要时申请系统动态端口，并把实际地址传递给依赖服务。

| 服务 | 首选端口 | 用途 |
| --- | ---: | --- |
| ASR | 19201 | 语音识别 |
| LLM | 19202 | OpenAI-compatible 对话/推理接口 |
| TTS | 19203 | 统一语音合成入口 |
| GSVI | 19205 | GPT-SoVITS 后端；可选、可隔离 |
| Bridge | 19206 | HTTP API 与 `/client-ws` WebSocket |
| Vite frontend | 5173 | 开发前端/Electron 热更新页面 |

不要在业务代码中硬编码端口。前端代理、服务启动和健康检查都应从 `config/services.json` 或运行时注入的实际地址读取。

## 运行链路

```text
用户文本/语音
  -> Bridge / CLI
  -> CharacterRuntime.handle_turn(TurnInput)
  -> ASR / 角色上下文 / 记忆 / 决策 / 工具 / 情绪与表现意图
  -> TTS
  -> TransportEmitter
  -> /client-ws (protocolVersion 3.0)
  -> React/Electron Live2D 表现层
```

Runtime 的唯一回合入口是 `CharacterRuntime.handle_turn(TurnInput)`。后端只发送语义化的 `character.intent`，不直接发送 Cubism 参数、表达式文件名或动作文件名；模型能力和渲染细节由前端角色配置与表现控制链解析。

Live2D 前端的核心控制边界是：

```text
CharacterBehaviorResolver
  -> CharacterPerformancePolicy
  -> PerformanceCoordinator / MotionArbiter
  -> ParameterMixer
  -> Live2DModelAdapter
  -> Cubism SDK
```

所有参数写入必须经过统一控制链，避免鼠标跟踪、自然动作、口型、表情和 LLM 意图互相直接写模型。

## 代码入口与目录

```text
ai/
├─ soulctl.cmd                 # Windows 统一启动/停止入口
├─ scripts/soulctl.cjs         # 启动器与命令分发
├─ run.py                      # CLI 兼容入口
├─ config/services.json        # 服务、端口、依赖和 profile 的来源
├─ config/characters/          # 角色卡与角色注册
├─ config/avatar_profiles/      # 模型能力和表现配置
├─ models/live2d-models/       # Live2D 模型资源
├─ app/lifecycle/              # Supervisor、健康检查和生命周期客户端
├─ app/runtime/                # CharacterRuntime 与 Runtime V3 回合链
├─ app/bridge/                 # HTTP/WebSocket Bridge
├─ contracts/v3/               # V3 envelope、事件和 registry
├─ frontend/src/               # React、Live2D 和表现控制器
├─ frontend/electron/           # Electron 主进程
├─ tests/                      # Python 测试
├─ frontend/src/**/*.test.*    # 前端单元/集成测试
├─ ARCHITECTURE.md             # 当前架构说明
└─ docs/                       # 协议、生命周期和历史审计资料
```

## 测试与构建

在仓库根目录运行 Python 测试：

```powershell
python -m pytest -p no:cacheprovider -q
```

在 `frontend/` 运行前端验证：

```powershell
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
```

实时表现问题不能只用构建结果判断。Live2D 变更还应在实际模型上检查参数覆盖、表情/动作切换、口型、鼠标跟踪、自然动作和运行时监控面板。

## 文档导航

- [ARCHITECTURE.md](ARCHITECTURE.md)：当前 Runtime V3、Bridge、Live2D 和生命周期边界。
- [docs/README.md](docs/README.md)：文档状态、当前资料和历史资料的分类。
- [docs/runtime/V3_PROTOCOL.md](docs/runtime/V3_PROTOCOL.md)：Runtime V3 事件与 WebSocket 协议。
- [docs/runtime/LAUNCH_ARCHITECTURE.md](docs/runtime/LAUNCH_ARCHITECTURE.md)：启动、就绪和关闭链路。

`docs/` 中带日期的审计、交接和方案文件是当时的证据或决策记录，不应被当作当前端口、分支或行为的唯一说明；遇到冲突时以代码、配置和测试为准。

## License

MIT
