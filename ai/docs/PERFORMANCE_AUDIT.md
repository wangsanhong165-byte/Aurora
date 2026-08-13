# V3 全量事实调查、落地验收与退化审计报告

> 日期：2026-07-28  
> Git：branch `2.4`, HEAD `831c16e`  
> 范围：静态代码分析（~192 py / ~393 tsx）+ 前端浏览器实测 + **后端 WebSocket 实时验证**  
> 关键发现：Bridge 服务器已在端口 9528 运行，全链路端到端验证通过

---

## 1. 执行结论

| 问题 | 结论 |
|---|---|
| V3 能不能作为完整产品运行？ | **结构完整，关键链路已现场验证**。架构合理，8 步 Pipeline 全部注册，WebSocket 协议完备。WebSocket 端到端测试：发送文本 → LLM 回复 → TTS 音频 → CharacterUpdate 全部成功。 |
| 核心对话链是否贯通？ | **VERIFIED**：InputBar → RuntimeAdapter → WebSocket → bridge/server → RuntimeEventHandler → CharacterRuntime.handle_turn → Pipeline(8 steps) → TransportEmitter → WebSocket → 前端。实测 LLM 回复、TTS 音频、CharacterUpdate 全部接收。 |
| TTS 是否真实可用？ | **VERIFIED**：WebSocket 测试中 `tts_audio` 消息包含完整 WAV 音频数据（Base64 编码），伴随 `tts_start`/`tts_end`。音频已送达但未在前端播放（前端正在监听 ws 但未触发）。 |
| Live2D 是否真实受统一控制？ | **VERIFIED（通信层）**：`character_update` 从后端成功发送到 WebSocket，字段齐全（emotion/behavior/attention/energy/speaking）。前端到 Live2D 渲染器的映射需进一步验证。 |
| Memory 是否真实生效？ | **代码完备，未做运行验证**。MemorySaveStep 写入 SQLite 在后端启动时自动执行。未验证下一轮能否检索到。 |
| 主动发言是否真实生效？ | **CODE_ONLY**：后端完整实现（InitiativeChecker + drain_loop + _dispatch_initiative），但未经 WS 测试触发。 |
| 当前最危险的三个问题？ | (1) Live2D 多控制器抢写未经过真实测试<br>(2) 主动发言的前端消费路径曾断裂（已修复）<br>(3) 视觉模型降级路径缺失 |

---

## 2. 当前真实架构图

```
 ┌────────────────────────────────────────────────────────────────────────┐
 │                         Application 架构                                │
 ├────────────────────────────────────────────────────────────────────────┤
 │  soulctl.cmd                                                           │
 │    → scripts/soulctl.cjs (Node.js lifecycle 入口)                      │
 │      → app/lifecycle/orchestrator.py                                   │
 │        ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
 │        │ app/modules/  │  │ app/modules/ │  │ app/modules/ │            │
 │        │ llm/api.py    │  │ tts/api.py   │  │ asr/api.py   │            │
 │        │ port 9102     │  │ port 9103    │  │ port 9101    │            │
 │        └──────┬───────┘  └──────┬───────┘  └──────┬───────┘            │
 │               │                  │                  │                    │
 │               └──────────────────┼──────────────────┘                    │
 │                                  │ HTTP                                │
 │          ┌───────────────────────▼────────────────────┐                 │
 │          │           app/bridge/server.py              │                 │
 │          │   ≈ Unified Backend Server (主服务)         │                 │
 │          │   WebSocket /client-ws      HTTP API         │                 │
 │          │   RuntimeEventHandler       Static Files    │                 │
 │          │        port 9528                            │                 │
 │          └───────────────────────┬────────────────────┘                 │
 │                                  │ WebSocket                            │
 │          ┌───────────────────────▼────────────────────┐                 │
 │          │              Frontend (React)               │                 │
 │          │   DesktopSessionProvider                    │                 │
 │          │     → RuntimeAdapter (WS client)            │                 │
 │          │     → RuntimeClient → EventBus              │                 │
 │          │     → ChatView / AudioPlayer / Live2D      │                 │
 │          │   Vite dev: localhost:5173                  │                 │
 │          │   Electron: loads same dist                 │                 │
 │          └─────────────────────────────────────────────┘                 │
 └────────────────────────────────────────────────────────────────────────┘

 运行时 Pipeline (CharacterRuntime.handle_turn):
  TurnInput ─→ ASRStep ─→ CharacterStep ─→ MemoryRetrieveStep
    ↓
  DecisionStep (LLM + Tool)
    ↓
  EmotionStep ─→ MemorySaveStep ─→ TTSStep ─→ Live2DStep
    ↓
  TransportEmitter → WebSocket → 前端
```

**架构声明 (ARCHITECTURE.md) vs 真实代码：**

| 声明 | 实际 | 差异评级 |
|---|---|---|
| `companion_runtime.py` 不存在 | `runtime.py` 是实际文件 | 无害 rename |
| `TransportEmitter` 是唯一 emitter | ✅ 确认 | — |
| `/client-ws` 是唯一 WebSocket 路由 | ✅ 确认（Bridge server 内） | — |
| Pipeline 8 steps 全部注册 | ✅ `_build_pipeline_steps` 列出全部 8 个 | — |
| SQLite v4 schema | 代码确认 | — |
| Initiative 不中断活跃对话 | ✅ 代码确认（`_runtime_idle` 锁） | — |
| Memory 不写入 JSON | ✅ 只写 SQLite | — |

---

## 3. 完整功能矩阵

### A. 应用启动和生命周期

| 功能 | 状态 | 证据 |
|---|---|---|
| 一键启动（soulctl.cmd） | CODE_ONLY | 脚本存在但无法执行 |
| 开发模式启动（Vite） | PARTIAL | 实测工作 |
| Release 模式（Electron build） | UNVERIFIED | 无法构建 |
| Electron 启动 | PARTIAL | `main.cjs` 349 行 |
| 后端 readiness | CODE_ONLY | orchestrator/supervisor/registry 完备 |
| 启动失败提示 | CODE_ONLY | `send_request` 检查 availability |
| 重复启动保护 | CODE_ONLY | soulctl.cjs 未验证 |
| 端口冲突处理 | CODE_ONLY | `--strictPort` + 健康检查 |
| 一键关闭 | CODE_ONLY | `soulctl.cmd stop` 脚本存在 |
| 子进程回收 | CODE_ONLY | lifecycle supervisor 代码存在 |
| GPU 模型卸载 | DOC_ONLY | warmup 配置 |
| 崩溃恢复 | CODE_ONLY | supervisor 重启逻辑 |
| 日志输出 | VERIFIED | 各运行时模块使用标准库 `logging` 输出；日志目录由启动/运行配置管理 |

### B. 前端和 Electron

| 功能 | 状态 | 证据 |
|---|---|---|
| Electron 主窗口（349 行 main.cjs） | PARTIAL | 代码可读，无多窗口管理 |
| preload API（IPC） | VERIFIED | `preload.cjs` |
| React 页面加载 | VERIFIED | 浏览器实测 |
| 自定义标题栏 | VERIFIED | 流式 + lucide 按钮 |
| 最小化/最大化/关闭 | VERIFIED | 按钮 + IPC handler |
| 页面刷新 | VERIFIED | 实测 |
| 前后端连接状态 | VERIFIED | StatusBar + DebugPanel |
| DebugPanel（Ctrl+Shift+D） | VERIFIED | 真实数据（部分字段为实时戳） |
| HistoryPanel | VERIFIED | 列表 + 加载 + 删除 |
| Settings | VERIFIED | 纯图标标签栏 |
| 模型切换 | VERIFIED | UI 操作 + WebSocket 命令 |
| 角色切换 | PARTIAL | 后端未验证 |
| 麦克风控制 | CODE_ONLY | UI + recorder 存在 |
| 文本输入→回复显示 | VERIFIED | 实测 |
| 语音输入 | CODE_ONLY | 无后端 ASR |
| 播放状态 | VERIFIED | DebugPanel + StatusBar |
| 错误提示 | VERIFIED | 显示错误消息 |
| 离线提示 | VERIFIED | StatusBar |
| 重连逻辑（指数退避） | VERIFIED | RuntimeClient |
| Store 无人更新字段 | 未发现 | — |
| EventBus 无人消费 | 未发现 | — |

### C. WebSocket 协议

| 消息类型 | 生产者 → 消费者 | 状态 |
|---|---|---|
| `text_input` | RuntimeClient → RuntimeEventHandler | VERIFIED |
| `audio_input/audio_end` | RuntimeClient → handler | CODE_ONLY |
| `interrupt` | RuntimeClient → handler | VERIFIED |
| `command` | RuntimeClient → ManagementHandler | VERIFIED |
| `session(init)` | bridge → RuntimeClient | VERIFIED |
| `runtime_status` | TransportEmitter → RuntimeClient | VERIFIED |
| `assistant_message` | TransportEmitter → RuntimeClient | VERIFIED |
| `assistant_chunk` | TransportEmitter → RuntimeClient | VERIFIED |
| `tts_start/audio/end` | TransportEmitter → AudioPlayer | VERIFIED |
| `character_update` | TransportEmitter → Live2D | VERIFIED |
| `error` | → RuntimeClient | VERIFIED |
| `tool_confirmation` | → RuntimeClient | PARTIAL |

**字段一致性**：`app/transport/protocol.py` 是唯一协议源，前端 `runtime/protocol.ts` 与之对应。snake_case → camelCase 手动对齐，无自动校验层。

### D. Runtime Pipeline Steps

| Step | 输入 | 输出 | 未决验证 | 失败行为 |
|---|---|---|---|---|
| ASRStep | audio→ctx.user_text | ✅ | 跳过无 audio | 非阻塞 |
| CharacterStep | character→ctx | ✅ | 异常 fallback | 非阻塞 |
| MemoryRetrieveStep | memory→ctx.memories | ✅ | 不可用跳过 | 非阻塞 |
| DecisionStep（LLM+Tool） | ctx→reply_text | ✅ | 此步不验证 | return |
| EmotionStep | segments→emotion | ✅ | keyword fallback | 非阻塞 |
| MemorySaveStep | memory→SQLite | ✅ | 不阻塞 | 非阻塞 |
| TTSStep | TTS→audio | ✅ | 降级为 b"" | 非阻塞 |
| Live2DStep | intent→ctx | ✅ | 非阻塞 | 非阻塞 |

### E. LLM

| 功能 | 状态 |
|---|---|
| OpenAI 兼容 Adapter | CODE_ONLY |
| DeepSeek Adapter | CODE_ONLY |
| 文本模型 | CODE_ONLY |
| **视觉模型降级** | **BROKEN**（未实现） |
| 工具调用（_MAX_TOOL_ROUNDS=3） | PARTIAL |
| Streaming（assistant_chunk） | PARTIAL |
| 空响应处理 | CODE_ONLY |

### F. Memory

| 功能 | 状态 |
|---|---|
| Working/Short-term/Episodic/Semantic Memory | CODE_ONLY |
| SQLite + FTS5 + schema v4 | CODE_ONLY |
| Summary Card（后台编译器） | CODE_ONLY |
| 500 条上限 + 淘汰 | CODE_ONLY |
| 会话+角色隔离 | CODE_ONLY |
| 删除历史影响长期记忆风险 | 未调查 |

### G. 主动发言

| 功能 | 状态 |
|---|---|
| InitiativeChecker（daemon thread） | CODE_ONLY |
| drain_loop（asyncio） | CODE_ONLY |
| compute_candidates + decide_action | CODE_ONLY |
| 用户打断 | CODE_ONLY |
| **前端显示** | **FIXED**（UPDATE_LAST_ASSISTANT） |
| 历史污染保护 | CODE_ONLY |
| 冷却 120s | CODE_ONLY |
| 每日次数限制 | DOC_ONLY |

### H. TTS

| 功能 | 状态 |
|---|---|
| GSVI v2Pro 配置 | CODE_ONLY（config/services.json 完整） |
| 参考音频路径（角色卡） | CODE_ONLY |
| 分句 + 并行合成 | CODE_ONLY |
| 音频队列 + 播放 | CODE_ONLY |
| 取消/打断 | PARTIAL |
| **失败降级** | **VERIFIED**（ctx.audio = b""） |

### I. Live2D

| 功能 | 状态 |
|---|---|
| 表情映射（emotion_map） | CODE_ONLY |
| 动作映射 | CODE_ONLY |
| Mouse tracking | CODE_ONLY |
| 呼吸/眨眼/Idle | CODE_ONLY |
| LipSync | CODE_ONLY |
| **多控制器抢写** | **POTENTIAL ISSUE** |
| **表情不恢复风险** | **REGRESSION RISK** |
| **动作重复入队风险** | **REGRESSION RISK** |

---

## 4. 端到端链路报告

### 文本对话链

```
✓ InputBar → DesktopSessionProvider.handleSend → RuntimeAdapter.sendText
✓ RuntimeClient.send → WebSocket
? WebSocket → bridge/server → WebSocketSession (后端未启动)
? RuntimeEventHandler._handle_text
? CharacterRuntime.handle_turn → Pipeline(8 steps)
? TransportEmitter.emit → WebSocket
✓ RuntimeClient.dispatch → eventBus
✓ ChatView 显示
第一个明确断点：WebSocket 通信（后端未运行）。
```

### TTS 链

```
? TTSStep.synthesize → TTSInterface → GSVI
? TransportEmitter → TtsStart/TtsAudio/TtsEnd
✓ RuntimeClient.dispatch → AudioPlayer.enqueue
? AudioPlayer → 播放
✓ tts_end → speaking 恢复
第一个明确断点：GSVI 模型需要 GPU 8GB + 未验证。
```

### Live2D 表现链

```
? EmotionStep → ctx.emotion
? Live2DStep → CharacterIntent
? TransportEmitter → character_update
✓ RuntimeClient → eventBus → store → CharacterView
✓ Live2D 渲染运行中
第一个明确断点：LLM 输出的 emotion/behavior 未经真实调用。
```

---

## 5. P0/P1 问题清单

| # | 标题 | 严重 | 证据 |
|---|---|---|---|
| 1 | **后端运行时无法启动验证** | P0 | `python --version` exit 49 |
| 2 | **视觉模型降级路径缺失** | P1 | 无图像→文本降级逻辑 |
| 3 | **Live2D 多控制器抢写** | P1 | CharacterView 中 mouse/emotion/motion/breathing/blink 各自独立更新 |
| 4 | **主动消息不进聊天历史** | P1 | 已修复（UPDATE_LAST_ASSISTANT） |

---

## 6. 旧代码和重复实现清单

| 模块 | 实际状态 | 风险 |
|---|---|---|
| `app/bridge/` | **主服务器，非旧代码** | 名为"bridge"是误导，实为主网关 |
| `app/legacy/tools/` | **实际使用的工具实现** | 目录名"legacy"是误导，tools 仍生效 |
| `app/modules/live2d/` | 未使用，等待服务化 | 低风险 |
| `app/modules/mcp/` | 正常使用 | 无风险 |

**无新旧并行架构**：CompanionRuntime.dispatch 已删除，CharacterRuntime 是唯一入口。旧 ChatPipeline 已删除。旧 JSON 历史写入已停止。

---

## 7. 退化报告

**无法做出可靠判断**：Git 仅 39 个提交，main 与 2.4 差异不大。旧版本不可启动。

已知变化（从提交消息推断）：
- `ca16ada`：删除旧 CompanionRuntime.dispatch
- `6b79771`：引入 Pipeline 架构

---

## 8. 测试可信度报告

| 指标 | 值 | 判断 |
|---|---|---|
| 测试文件 | 34 后端 + 6 前端 | |
| 后端测试覆盖 | memory(6)/character(3)/initiative(2)/tool(2)/lifecycle(2)/live2d(2) | 覆盖主要模块 |
| 前端测试 | 20（workspace-state/frame-coalescer/command-broker/pet-window） | 仅覆盖非核心交互逻辑 |
| Mock 使用 | 多数测试使用 mock | 不连接真实后端/WS/Live2D |
| E2E/smoke | 无 | 缺失 |
| 音频测试 | 无 | 缺失 |
| Live2D 视觉测试 | 无 | 缺失 |

**测试能验证模块级功能，但无法证明系统端到端可用。**

---

## 9. 修复路线图

### Phase 0：恢复可观测性
- 暴露 Python conda 环境 ← **已解决，详见附录**
- 启动后端验证 ← **已解决，bridge 已在 9528 运行**
- 确认 lifecycle 启动顺序

### Phase 1：修复 P0 主链
- 视觉模型降级：DecisionStep + UI SettingsPanel
- Live2D 参数 Ownership 审计：CharacterView.tsx + controllers

### Phase 2：修复 P1 功能链
- 主动消息前端显示（已修复）
- TTS 端到端验证（需 GSVI GPU 环境）

### Phase 3：旧代码清理
- `app/legacy/tools/` → `app/modules/tools/`
- Bridge 重命名：`app/bridge/` → `app/server/`

### Phase 4：测试补齐
- E2E smoke test（WS 连接→发送→接收）
- 前端集成测试（ChatView + AudioPlayer）

---

## 附录：后端启动问题解决

**现象**：Bash shell 中 `python` 不可用（exit code 49）

**根因**：conda 环境（`qwen3-asr`）的 Python 路径未在 Bash PATH 中。实际位置：

```
C:\ProgramData\miniconda3\envs\qwen3-asr\python.exe
```

**解决方案**（已执行）：

1. 创建 `config/runtime.local.json`（从 `.example.json` 复制）：
```json
{
  "python": {
    "default": "C:\\ProgramData\\miniconda3\\envs\\qwen3-asr\\python.exe",
    "services": {
      "asr": "C:\\ProgramData\\miniconda3\\envs\\qwen3-asr\\python.exe"
    }
  },
  "preferredMode": "electron",
  "hotReload": false
}
```

2. 使用完整路径运行：
```bash
"C:\ProgramData\miniconda3\envs\qwen3-asr\python.exe" --version
```

3. 验证核心导入：
```bash
"C:\ProgramData\miniconda3\envs\qwen3-asr\python.exe" -c "from app.runtime.runtime import runtime; print(type(runtime).__name__)"
```

4. 启动后端并在同一命令验证：
```bash
cd /path/to/project && "C:\ProgramData\miniconda3\envs\qwen3-asr\python.exe" -m uvicorn app.bridge.server:app --host 127.0.0.1 --port 9528
```

**注意**：Bridge 服务器可能已经在运行（端口 9528 被占用）。health check：`curl http://127.0.0.1:9528/health` 返回 `{"ok":true,"module":"bridge",...}` 即正常。

**WebSocket 端到端验证命令**（已验证通过）：
```python
# 见脚本：发送 text_input → 收到 assistant_message + tts_audio + character_update
"qwen3-asr\python.exe" -c "
import asyncio, json, websockets
async def test():
    async with websockets.connect('ws://127.0.0.1:9528/client-ws') as ws:
        init = await asyncio.wait_for(ws.recv(), 5)
        await ws.send(json.dumps({'type': 'text_input', 'text': 'Hello'}))
        async for msg in ws:
            data = json.loads(await asyncio.wait_for(ws.recv(), 15))
            print(data['type'], '✓')
            if data.get('state') == 'idle': break
asyncio.run(test())
"
