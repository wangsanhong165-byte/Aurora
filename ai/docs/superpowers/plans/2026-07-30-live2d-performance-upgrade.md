# Live2D 表现系统升级实施计划

> **面向 AI 代理的工作者：** 在当前工作区内按任务顺序执行；每个任务使用测试先行，保持 `ParameterMixer -> Live2DModelAdapter` 为唯一 Cubism 参数写入链。

**目标：** 将现有“能驱动”的 Live2D 基础链升级为可中断、可按模型适配、动作不打架、语音表现稳定且可校准的表现系统。

**架构：** 运行时事件先进入带 `turnId/sequence` 的音频播放队列和角色意图层；所有原生动作、程序化动作、表情、视线、眨眼与唇同步都生成带所有权和有效期的贡献，由动作仲裁器和 `ParameterMixer` 统一解决冲突。模型差异集中在 `AvatarCapabilityProfile`，控制器只使用逻辑参数。

**技术栈：** TypeScript 5.5、React 18、Web Audio、Cubism SDK、Node 内置测试运行器。

---

## 文件结构

- 修改 `frontend/src/core/event-bus.ts`：音频事件携带轮次和序列。
- 修改 `frontend/src/runtime/adapter.ts`：保留 V3 TTS 所有权信息。
- 修改 `frontend/src/audio/player.ts`：实现可取消、有序、可复用的音频播放器。
- 新建 `frontend/src/audio/player.test.ts`：覆盖中断、过期分片、回调保留。
- 修改 `frontend/src/session/DesktopSessionProvider.tsx`：停止时不销毁播放器。
- 修改 `frontend/src/character/AvatarCapabilityProfile.ts`：扩展模型能力、参数范围和嘴型配置。
- 修改 `frontend/src/character/AvatarParameterResolver.ts`：按模型范围过滤和映射逻辑参数。
- 新建 `frontend/src/character/avatar-profile.test.ts`：覆盖模型画像映射与限制。
- 修改 `frontend/src/character/MotionArbiter.ts`：改为带 owner、channel、turnId、TTL 和抢占策略的动作请求。
- 新建 `frontend/src/character/motion-arbiter.test.ts`：覆盖抢占、取消、区域共存和过期。
- 重写 `frontend/src/character/performance/VADGestureController.ts`：动作族、上下文权重、重复规避。
- 重写 `frontend/src/character/performance/VADMicroMotionController.ts`：多频率、模型能力感知的微动作。
- 重写 `frontend/src/character/performance/VoiceWaitingMotionController.ts`：监听/思考动作模板和过渡。
- 修改 `frontend/src/character/performance/SpeechPerformanceController.ts`：语音重音和动作释放。
- 修改 `frontend/src/character/AudioAnalyzer.ts`：噪声门、峰值强调、attack/release 和静音闭嘴。
- 新建 `frontend/src/character/live2d-performance.test.ts`：覆盖动作确定性、范围和唇同步。
- 修改 `frontend/src/character/controllers.ts`：接入新仲裁接口和模型画像配置。
- 修改 `frontend/src/character/CharacterView.tsx`：清理重复订阅及生命周期残留。
- 修改 `frontend/package.json`：将新增测试纳入标准测试命令。
- 修改 `scripts/inspect_live2d_profiles.mjs`：输出能力覆盖和校准建议。
- 修改 `config/avatar_profiles/ariu.json`：校准 Ariu 参数范围和表现风格。
- 保留并验证 `config/avatar_profiles/hiyori_zh-Hans.json`：作为第二模型回归样本。
- 修改 `docs/runtime/V3_MIGRATION_REPORT.md`：记录升级后的真实完成边界。

### 任务 1：音频所有权与生命周期

- [x] 编写 AudioPlayer 和 RuntimeEventAdapter 失败测试：停止不清空 handlers、旧 turn 音频被拒绝、序列按序播放。
- [x] 运行定向测试并确认当前实现失败。
- [x] 为 `audio:play`/`audio:stop` 增加 `turnId` 和 `sequence`。
- [x] 将 `AudioPlayer` 拆成可复用 `stop()` 与终态 `dispose()`，队列按 owner/sequence 管理。
- [x] 修改 DesktopSessionProvider，仅在 effect 卸载时调用 `dispose()`。
- [x] 运行定向测试、类型检查和现有 runtime 测试。

### 任务 2：模型画像与安全参数映射

- [x] 编写画像解析失败测试：范围钳制、缺失能力、嘴型保护、身体增益。
- [x] 扩展 `AvatarCapabilityProfile`，把参数范围、控制通道、嘴型配置集中在画像。
- [x] 深化 `AvatarParameterResolver`，未知逻辑参数不输出，所有输出按画像范围钳制。
- [x] 校准 Ariu；验证 Hiyori 能由同一接口加载。
- [x] 扩展检查脚本，严格模式拒绝无效绑定并报告能力缺口。

### 任务 3：动作仲裁与程序化表现

- [x] 编写 MotionArbiter 失败测试：同区域高优先级抢占、不同区域共存、按 turn 取消、TTL 自动释放。
- [x] 用 `MotionRequest` 替换仅字符串队列的浅接口，同时保留 `play()` 兼容入口。
- [x] 重写 VAD 手势、微动作和等待动作控制器，加入 seeded random、动作族和重复规避。
- [x] 将原生动作与程序化动作都转换成贡献，禁止第二条 SDK 写入路径。
- [x] 接入 CharacterController，并确保模型切换和 detach 会取消所有动作所有权。

### 任务 4：唇同步与说话表现

- [x] 编写 AudioAnalyzer 失败测试：噪声门、快速起音、平滑释放、停止后归零。
- [x] 实现 RMS/峰值混合、attack/release、峰值重音和模型嘴型范围。
- [x] 让 SpeechPerformanceController 使用音频能量产生轻量头身重音。
- [x] 确保 motion/expression 不能覆盖 `mouth.open`，说话结束后在限定时间内闭嘴。

### 任务 5：生命周期清理、校准输出和整体验证

- [x] 删除 CharacterView 重复的 `character:activity` 订阅并清理全部 timer/owner。
- [x] 将新增测试加入 `npm test`。
- [x] 运行 `npm test`、`npm run typecheck`、`npm run build` 和画像 strict 检查。
- [x] 对 Ariu/Hiyori 执行浏览器模型加载、表情、程序化动作和模型切换冒烟测试。
- [x] 使用真实浏览器 `AudioContext` 音频完成播放、口型驱动、中断及闭嘴端到端验收。
- [x] 更新 V3 报告：只有上述自动测试和视觉验收都通过时，Live2D 表现系统才标为完成。

## 实施结果（2026-07-30）

状态：**本计划定义的 Live2D 表现系统升级和浏览器验收已完成。**

- 音频片段现在按 `turnId/sequence` 排序、拒绝过期轮次，并区分可复用停止与终态销毁。
- 模型画像统一承载参数能力、范围、保护通道和嘴型配置；Ariu 与 Hiyori 均通过严格检查。
- 原生动作与程序化动作统一经过带 owner、channel、turnId、TTL 的仲裁层。
- 原生 motion3 的 `Parameter` 与 `PartOpacity` 曲线均转换为帧贡献；Pose、
  Expression 与 Native Motion 的部件透明度由同一混合器按优先级解决。
- 唇同步加入噪声门、attack/release、峰值强调与嘴型保护；说话、等待和空闲微动可中断。
- V3 `character.intent.motionPlan` 只接受十种安全动作原语、有限时长/步骤/强度；
  前端把原语编译为逻辑参数轨道，LLM 无法写入 Cubism 参数或关键帧。
- 设置页新增按模型保存的表现模式/强度、快速试演、真实口型诊断、非持久化参数
  校准实验室，以及动作创建、编辑、试演、导入和导出工作台。
- Hiyori 真实浏览器音频验收结果为：音量峰值 0.357、开口峰值 0.750、
  中断后嘴型 0.000。
- Ariu 与 Hiyori 已在生产构建页面完成真实加载、动作试演和切换；Ariu 增加
  模型专属初始取景以避免主体裁切；最终浏览器控制台为 0 错误、0 警告。

### 完成边界

“完成”指本计划范围内的控制链、动作安全、创作工具、真实浏览器音频与双模型
回归完成，不表示所有 Live2D 资产已经完成逐动作美术调校。新增模型仍应提供
`AvatarCapabilityProfile`，并用动作工作台和真实口型诊断进行模型级验收。
