# 人格记忆完整闭环实现计划

> **面向 AI 代理的工作者：** 使用 executing-plans 在当前会话逐项执行；每项功能严格采用测试先行。

**目标：** 在保留现有对话和事实数据的前提下，使系统具备可检索、可更新、可持久化、可解释、可控成本的人格记忆闭环，并让主动对话和工具调用共享同一上下文。

**架构：** SQLite 继续作为唯一持久化事实源，新增结构化记忆与人格状态表。检索采用词法、语义近似、重要性、时效性和人格范围的混合评分；提示词使用软预算分层装配。每轮结束后由记忆学习器生成候选更新，经过规范化、去重、冲突替换后持久化。

**技术栈：** Python、SQLite/FTS5、现有 OpenAI 兼容 LLM 适配器、pytest。

---

### 任务 1：结构化记忆存储与兼容迁移

**文件：**
- 修改：`app/memory/store.py`
- 创建：`app/domain/memory/models.py`
- 测试：`tests/test_memory_closed_loop.py`

- [ ] 编写失败测试：旧数据库启动时自动增加结构化记忆、人格状态和检索审计表，旧日志与 facts 数量保持不变。
- [ ] 运行测试并确认因新 API/表缺失而失败。
- [ ] 实现幂等迁移以及 `upsert_memory`、`list_memories`、`save_character_state`、`load_character_state`。
- [ ] 运行专项测试，确认迁移和读写通过。

### 任务 2：混合检索与可解释排序

**文件：**
- 创建：`app/memory/retrieval.py`
- 修改：`app/memory/store.py`
- 修改：`app/providers/memory/sqlite_memory.py`
- 测试：`tests/test_memory_closed_loop.py`

- [ ] 编写失败测试：“我喜欢什么”可以召回措辞不同的偏好事实；不同人格日志隔离；结果包含分数和命中原因。
- [ ] 运行测试并确认现有纯 FTS 检索无法通过。
- [ ] 实现无需外部下载的混合评分：CJK/英文规范化、字符 n-gram 相似度、词法命中、重要性、时效性、记忆类型和人格范围。
- [ ] 将 SQLiteMemory 切换为混合检索，同时保留 compiled memory 兜底。
- [ ] 运行专项测试，确认召回、排序、隔离和解释字段通过。

### 任务 3：记忆生命周期与冲突处理

**文件：**
- 创建：`app/memory/lifecycle.py`
- 修改：`app/memory/extractor.py`
- 修改：`app/memory/store.py`
- 测试：`tests/test_memory_closed_loop.py`

- [ ] 编写失败测试：相同事实合并、发生变化的事实替换旧值、共同经历保留、低置信候选不污染长期记忆。
- [ ] 运行测试并确认生命周期 API 缺失。
- [ ] 定义用户事实、偏好、近期状态、情节、关系、未完成事项六类记忆候选。
- [ ] 实现稳定键、置信度阈值、合并计数、冲突失效和最近访问时间。
- [ ] 让提取器输出候选后统一经过生命周期写入，不再直接按共享标签拒绝事实。
- [ ] 运行专项测试。

### 任务 4：人格状态学习与重启恢复

**文件：**
- 创建：`app/runtime/character_learning.py`
- 修改：`app/domain/character/character.py`
- 修改：`app/runtime/steps/character_step.py`
- 修改：`app/runtime/steps/memory_save_step.py`
- 修改：`app/runtime/runtime.py`
- 测试：`tests/test_character_memory_persistence.py`

- [ ] 编写失败测试：偏好、关系、目标和长期心情保存后，新建 Character 仍能恢复。
- [ ] 运行测试并确认当前内存对象重启丢失。
- [ ] 实现人格状态序列化/恢复；只允许有证据的渐进更新并限制单轮关系变化。
- [ ] 在 MemorySaveStep 后学习用户偏好、关系信号、未完成事项并持久化。
- [ ] 运行专项测试与现有人格测试。

### 任务 5：主动系统使用记忆做决策

**文件：**
- 创建：`app/runtime/initiative_memory.py`
- 修改：`app/runtime/runtime.py`
- 修改：`app/runtime/prompts.py`
- 测试：`tests/test_initiative_memory_loop.py`

- [ ] 编写失败测试：主动事件可获取近期状态/未完成事项；重复话题受冷却；无足够价值时保持安静。
- [ ] 运行测试并确认当前主动系统只使用近期对话和活动状态。
- [ ] 实现主动记忆候选选择、价值阈值、话题冷却和触发解释。
- [ ] 将选择结果放入 initiative 结构，再经过既有 MemoryRetrieveStep 和工具安全策略。
- [ ] 运行专项测试。

### 任务 6：软 Token 预算和工具结果保护

**文件：**
- 创建：`app/runtime/context_budget.py`
- 修改：`app/runtime/context_assembler.py`
- 修改：`app/runtime/steps/decision_step.py`
- 测试：`tests/test_context_budget.py`

- [ ] 编写失败测试：人格核心和高价值记忆始终保留；低价值历史接近预算时压缩；超长工具结果被摘要或截断并标记。
- [ ] 运行测试并确认当前历史/工具结果没有总量保护。
- [ ] 实现字符与语言感知的 token 估算、分层软预算和异常硬保护。
- [ ] 默认软预算设置为宽松值，并通过环境变量配置；不得静默删除重要记忆。
- [ ] 运行专项测试。

### 任务 7：真实用量、费用与检索观测

**文件：**
- 修改：`app/interfaces/llm.py`
- 修改：`app/models/http_adapters.py`
- 修改：对应 LLM provider
- 修改：`app/runtime/context.py`
- 修改：`app/runtime/steps/decision_step.py`
- 测试：`tests/test_llm_usage.py`

- [ ] 编写失败测试：API usage 被归一化到 LLMResponse；多轮工具调用累计用量；上下文记录检索原因和估算/真实 token。
- [ ] 运行测试并确认 usage 当前在 provider 边界丢失。
- [ ] 增加 Usage 数据模型，保留 prompt、completion、cached tokens 和模型名。
- [ ] 在 DecisionStep 汇总每轮 usage，并生成费用统计数据；没有 usage 时使用估算且明确标记。
- [ ] 运行专项测试。

### 任务 8：闭环验收和回归

**文件：**
- 创建：`tests/test_memory_end_to_end.py`
- 修改：必要的现有回归测试

- [ ] 建立临时数据库完成“告知偏好→保存→重启→换一种说法询问→召回”的端到端测试。
- [ ] 验证事实修改不会保留两个有效冲突版本。
- [ ] 验证主动系统引用未完成事项且不会重复骚扰。
- [ ] 验证千轮合成历史下上下文进入稳定区间，重要记忆仍存在。
- [ ] 运行记忆/人格/主动/工具专项测试。
- [ ] 运行完整 pytest，检查失败和警告。
- [ ] 检查 git diff，确认没有覆盖用户现有数据库、历史和运行状态文件。
