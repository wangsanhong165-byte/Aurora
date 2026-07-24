# Live2D 最后一公里表现设计

## 目标

以 Soullink Emotion SDK 的运行时表现层为主要标杆，在不替换官方 Cubism
Web SDK 渲染器、不引入第二套参数写入链的前提下，让现有四个模型在静置、
说话、情绪变化和交互时产生肉眼可辨、可校准、可回退的表现差异。

## 参考边界

主要吸收 Soullink 的实际运行机制：最终参数增益、完整 MotionStyle 消费、
VAD 微动作、VAD 离散手势、模型私有情绪参数、等待说话动作、Neutral 恢复、
显式原生动画映射和可操作校准。补充吸收 Open-LLM-VTuber 的 Talk Motion、
点击反馈与说话/眨眼冲突处理。保留本项目的 CharacterIntent、MotionArbiter、
ParameterMixer 和 Live2DModelAdapter 单写入链。

## 数据流

`CharacterIntent / activity / audio / interaction`
→ `VAD + performance mode`
→ `idle / VAD micro / VAD gesture / speech / private emotion / native motion`
→ `AvatarParameterResolver`
→ `ParameterMixer`
→ `Live2DModelAdapter`
→ Cubism。

所有表现层输出逻辑通道或已校验模型参数；只有 Adapter 写入 SDK。

## 可见性与增益

Profile 增加 `parameterGain`、`bodyMotionGain`、`performanceMode` 和
`privateEmotionMap`。默认使用 `enhanced`，最终参数围绕 neutral 放大，
而非直接乘绝对值。提供 `legacy`、`enhanced`、`calibration` 三种模式：

- `legacy`：关闭新增表现层，便于 A/B。
- `enhanced`：安全、明显的生产表现。
- `calibration`：短时提高动作频率和幅度，便于检查映射。

所有增益在 Profile 安全范围内截断。调试信息必须显示各层贡献、最终增益和
当前模式。

## 表现层

- Idle 必须实际消费 blinkRate、breathRate、breathVariance、
  microMotionGain、idleActionGain、bodyMotionGain、gestureFrequency。
- VADMicroMotion 产生连续、低幅、非同步的头身和视线偏置。
- VADGesture 在情绪变化或高 arousal 时产生有限时长的点头、后仰、侧倾等，
  带冷却和重复规避。
- PrivateEmotionOverlay 将 VAD/情绪声明式映射到模型私有参数，支持阈值、
  强度、neutral、范围和衰减。
- VoiceWaitingMotion 覆盖 listening/thinking/等待首个音频帧，说话时由
  SpeechPerformanceController 和可用 Talk Motion 接管。
- Recovery 将短时反应逐渐释放到当前 VAD 基线，而不是直接回零。

## 原生动画映射

扫描器输出稳定的 Motion/Expression 名称和文件名。Profile 只映射已存在资源；
未确认语义的 `mtn_XX` 不猜测含义，而是通过校准面板逐个预览后保存。明确存在
Talk、Tap、Idle 组时，分别映射 `speak`、`react/touch`、`idle`。

## 校准与验收

DebugPanel 增加模式切换、参数增益滑杆、表现事件触发按钮和当前模型原生资源
预览。设置只作用当前会话，除非用户明确保存。

验收场景：

1. 静置十秒内出现至少一次可见微动作或闲置动作。
2. `legacy/enhanced` 切换时头身幅度和动作频率有明显差异。
3. 说话起势、重音、持续律动和结束恢复均可见，嘴形仍由音频控制。
4. happy/sad/angry/surprised 至少影响两个非嘴部通道。
5. 点击和模型切换触发短反应，不留下参数残留。
6. 不支持的眉眼、身体或原生动画安全降级，不产生无效写入。
