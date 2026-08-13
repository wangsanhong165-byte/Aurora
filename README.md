<div align="center">

# Aurora

### 住在你电脑里的本地 AI 陪伴者

**会说话 · 有表情 · 记得你 · 可本地运行**

一个面向 Windows 的 AI 语音陪伴项目，将实时语音、Live2D 虚拟形象、持久记忆与可配置的 LLM 组合成自然的桌面陪伴体验。

<p>
  <a href="ai/">进入 Aurora 项目目录</a> ·
  <a href="ai/README.md">查看完整文档</a> ·
  <a href="ai/docs/">浏览项目资料</a>
</p>

</div>

---

## 项目亮点

| 能力 | 体验 | 项目特点 |
|---|---|---|
| 实时语音 | 像和一个真正的角色聊天 | VAD + ASR + LLM + TTS 串成完整语音交互链路 |
| Live2D 形象 | 对话时会说话、眨眼、口型同步 | React / Electron 与 Cubism 渲染链路结合 |
| 持久记忆 | 记住你们聊过的内容 | SQLite + FTS5 支持历史、检索与记忆编译 |
| 本地优先 | 数据和服务由自己掌控 | 后端服务在本机运行，LLM 可按需配置本地或兼容服务 |
| 主动陪伴 | 不只是等待用户提问 | 支持空闲检测、主动关怀与角色状态变化 |
| 角色定制 | 不同模型拥有不同风格 | Live2D 模型、声线、人格提示词可以组合配置 |

Aurora 不只是一个聊天窗口，而是一个有形象、有声音、能记住上下文的桌面 AI 角色。它把“对话内容”和“角色表现”放在同一条运行链路中，让文字、声音、表情和动作能够协同工作。

## 你可以用它做什么

- 日常语音聊天与陪伴
- 使用 Live2D 角色作为桌面虚拟助手
- 测试不同 LLM、ASR、TTS 与角色配置
- 构建带有记忆、人格和主动行为的本地 AI 应用
- 研究 Electron、React、Python 服务编排与 Live2D 表现控制

## 角色与声音

项目将 Live2D 模型、声音和角色配置分离，便于扩展和组合：

- 多个 Live2D 模型：`Design_genius_White`、`ariu`、`hiyori`、`mao`、`youxiaomiao`、`shirone`
- 支持 Alice 等角色配置
- 支持 Monika 等定制声线
- 角色由模型、声线和人格配置共同定义，不需要复制整套运行代码

## 运行链路

```text
麦克风 / 文本输入
        ↓
Bridge / CLI
        ↓
Character Runtime
        ↓
ASR · 记忆 · LLM · 工具 · 情绪与角色意图
        ↓
TTS 语音合成
        ↓
React / Electron + Live2D 表现层
```

项目采用 Python 后端服务与 React + Electron 前端协作的结构，并通过统一启动器管理服务生命周期。Live2D 表现由角色意图、动作调度、参数混合器和 Cubism 渲染链路共同完成。

## 快速开始

项目实际代码位于 [`ai/`](ai/)，请先进入该目录：

```powershell
cd ai

# 检查 Python、Node.js、配置和服务依赖
.\soulctl.cmd doctor

# 启动完整服务并打开 Electron 桌面端
.\soulctl.cmd electron
```

开发调试模式：

```powershell
cd ai
.\soulctl.cmd electron --hot
```

停止服务：

```powershell
cd ai
.\soulctl.cmd stop
```

更多启动方式、环境要求和配置说明，请查看 [`ai/README.md`](ai/README.md)。

## 技术栈

| 层次 | 技术 |
|---|---|
| 前端 | React、Vite、Electron、TypeScript |
| 虚拟形象 | Live2D Cubism Web Framework、WebGL |
| 语音识别 | Qwen3-ASR、VAD |
| 语音合成 | GPT-SoVITS v2Pro / GSVI 等可配置引擎 |
| 对话引擎 | OpenAI-compatible LLM 接口，可配置本地或兼容服务 |
| 记忆系统 | SQLite、FTS5、历史与记忆编译 |
| 服务编排 | Python Supervisor、`config/services.json` |
| 工具扩展 | MCP 工具系统 |

## 项目结构

```text
.
└─ ai/
   ├─ app/          Python 后端、运行时、记忆与服务生命周期
   ├─ config/       服务、角色、声线和运行配置
   ├─ contracts/    V3 协议与事件契约
   ├─ frontend/     React、Electron 与 Live2D 前端
   ├─ models/       Live2D、ASR、TTS 等模型资源
   ├─ scripts/      启动器、诊断和开发工具
   ├─ tests/        Python 与运行时测试
   ├─ docs/         架构、协议和生命周期资料
   ├─ soulctl.cmd   Windows 统一启动入口
   └─ README.md     完整项目说明
```

## 文档入口

- [完整项目说明](ai/README.md)
- [架构说明](ai/ARCHITECTURE.md)
- [文档总览](ai/docs/README.md)
- [启动与生命周期架构](ai/docs/runtime/LAUNCH_ARCHITECTURE.md)

## 当前定位

Aurora 仍然是一个持续演进中的本地 AI 陪伴项目。它适合用于个人桌面陪伴、角色化交互实验、Live2D 表现研究，以及本地语音 AI 产品原型开发。

如果你想直接查看代码和运行项目，请进入 [`ai/`](ai/)；如果你想先了解整体能力，可以从本页的项目亮点和快速开始读起。

<div align="center">

**让 AI 不只回答你，也真正“出现在你面前”。**

</div>
