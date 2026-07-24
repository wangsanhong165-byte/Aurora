# Agent 上下文、主动系统与工具调用实现计划

> **面向 AI 代理的工作者：** 在当前会话中逐任务执行本计划；每项均遵循测试先失败、最小实现、回归验证。

**目标：** 修复主动事件、角色记忆和角色切换语义，并为普通/主动对话提供受控的三轮工具调用与可靠的结构化输出。

**架构：** 保留 Runtime Pipeline 作为唯一入口；Context 明确区分用户输入和主动事件；MemoryInterface 与 ToolInterface 承担稳定 seam；DecisionStep 内的 ContextAssembler、ToolPolicy 和 ResponseValidator 隐藏组装、权限与规范化复杂度。

**技术栈：** Python、asyncio、unittest/pytest、现有 OpenAI-compatible LLM 和 ToolInterface。

---

### 任务 1：结构化主动事件

**文件：**
- 修改：`app/core/intent.py`
- 修改：`app/runtime/prompts.py`
- 修改：`app/runtime/runtime.py`
- 测试：`tests/test_runtime_pipeline.py`

- [ ] 编写 reminder payload 保留任务名称、未知事件不变成无关问候的失败测试。
- [ ] 运行定向测试并确认因 payload 未处理而失败。
- [ ] 扩展 candidate 和 initiative event payload，令 Runtime 传递 `display_text` 与 `initiative`。
- [ ] 运行定向测试确认通过。

### 任务 2：主动消息身份与角色记忆

**文件：**
- 修改：`app/runtime/context.py`
- 修改：`app/interfaces/memory.py`
- 修改：`app/runtime/steps/memory_retrieve_step.py`
- 修改：`app/runtime/steps/memory_save_step.py`
- 修改：`app/providers/memory/sqlite_memory.py`
- 测试：`tests/test_runtime_pipeline.py`

- [ ] 编写主动 prompt 不保存为 user、检索显式收到 character/event/origin 的失败测试。
- [ ] 运行定向测试确认失败。
- [ ] 增加 `input_origin`，扩展 retrieve 可选参数，主动存储仅保留 assistant 与事件元数据。
- [ ] 让 compiled memory 按显式 character_id 获取。
- [ ] 运行定向测试确认通过。

### 任务 3：角色热切换

**文件：**
- 修改：`app/runtime/steps/character_step.py`
- 修改：`app/runtime/runtime.py`
- 测试：`tests/test_production_regressions.py`

- [ ] 编写切换后 CharacterStep 注入新 Character 的失败测试。
- [ ] 运行测试确认旧固定引用导致失败。
- [ ] 为 CharacterStep 提供受控 `set_character()`，切换成功后同步 Runtime 与该 Step。
- [ ] 运行测试确认通过。

### 任务 4：受控工具策略与三轮循环

**文件：**
- 创建：`app/runtime/tool_policy.py`
- 修改：`app/interfaces/tool.py`
- 修改：`app/providers/tool/legacy_provider.py`
- 修改：`app/runtime/steps/decision_step.py`
- 测试：`tests/test_runtime_pipeline.py`

- [ ] 编写主动对话仅暴露明确允许的只读工具、未分类工具默认需确认的失败测试。
- [ ] 编写工具最多三轮、确认缺失不执行、工具结果被截断和标记为不受信任的失败测试。
- [ ] 运行定向测试确认失败。
- [ ] 实现 ToolPolicy schema 过滤、执行授权和结果清洗。
- [ ] 把 DecisionStep 工具轮数改为三轮，并经策略执行。
- [ ] 从 LegacyToolProvider 映射内置 registry 风险；MCP 工具默认 `confirm`。
- [ ] 运行定向测试确认通过。

### 任务 5：上下文装配和输出校验

**文件：**
- 创建：`app/runtime/context_assembler.py`
- 创建：`app/runtime/response_validator.py`
- 修改：`app/providers/llm/openai_adapter.py`
- 修改：`app/runtime/steps/decision_step.py`
- 测试：`tests/test_runtime_pipeline.py`

- [ ] 编写记忆去重/预算、主动事件 system 注入、非法输出安全降级的失败测试。
- [ ] 运行定向测试确认失败。
- [ ] 实现 ContextAssembler，稳定装配语言、人格、记忆、历史、事件和输出规则。
- [ ] 实现 ResponseValidator，对 segments、枚举和数值范围做规范化。
- [ ] 保留 provider 原始文本，由 DecisionStep 在统一 seam 校验并构建 TTS 安全文本。
- [ ] 运行定向测试确认通过。

### 任务 6：回归与交付

**文件：**
- 检查：上述全部文件

- [ ] 运行 `pytest -q tests/test_runtime_pipeline.py tests/test_production_regressions.py`。
- [ ] 运行 `pytest -q`。
- [ ] 运行 `python -m compileall -q app tests`。
- [ ] 检查 `git diff --check` 和 `git diff --stat`。
- [ ] 对照规格逐项核验，没有通过的项目如实报告。
