# Live2D 最后一公里实现计划

> **面向 AI 工作者：** 使用 executing-plans 逐项实现，严格执行 TDD。

**目标：** 让 Soullink 风格的表现层真实进入最终 Cubism 输出，并可现场 A/B 验证。

**架构：** 保留现有单写入链，在 CharacterController 内增加小型表现层，
由 Profile 和会话级校准状态控制。

**技术栈：** TypeScript、React、Cubism Web SDK、JSON Profile、pytest。

### 任务 1：最终增益与完整 MotionStyle 消费

- [ ] 添加失败测试，要求所有 MotionStyle 字段进入对应控制器。
- [ ] 添加围绕 neutral 的 parameterGain 和 bodyMotionGain。
- [ ] 让 blink、breath、micro motion、gesture frequency 真正生效。
- [ ] 验证定向测试和类型检查。

### 任务 2：VAD 微动作、手势与恢复

- [ ] 添加失败测试覆盖连续微动作、手势冷却和 neutral 恢复。
- [ ] 实现 VADMicroMotionController、VADGestureController。
- [ ] 通过 mixer 的独立 add 层接入 CharacterController。
- [ ] 验证不同 VAD 输入产生可测差异。

### 任务 3：私有情绪和等待说话动作

- [ ] 添加失败测试覆盖声明式私有参数和活动状态。
- [ ] 实现 PrivateEmotionOverlay 和 VoiceWaitingMotionController。
- [ ] 扩展 Profile schema 并为已确认参数添加安全映射。
- [ ] 验证无能力模型安全降级。

### 任务 4：原生动画显式映射

- [ ] 添加失败测试覆盖 Talk、Tap、Idle 自动建议和显式映射。
- [ ] 改进扫描器，输出稳定别名与映射建议。
- [ ] 为可确认语义的模型补充 motionMap/expressionMap。
- [ ] 验证原生播放和程序化 fallback。

### 任务 5：A/B 校准工具

- [ ] 添加失败测试覆盖 legacy/enhanced/calibration 模式事件。
- [ ] 增加会话级模式、增益控制和表现触发事件。
- [ ] 在 DebugPanel 添加只影响当前会话的交互控件。
- [ ] 输出各表现层贡献和实际最终参数。

### 任务 6：质量门与提交

- [ ] 运行 Live2D 定向 pytest。
- [ ] 运行 TypeScript 类型检查与 Vite 生产构建。
- [ ] 运行四模型 profile 扫描。
- [ ] 检查提交范围并创建独立修复提交。
