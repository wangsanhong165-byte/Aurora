# 完整 LLM 提示词查看器实现计划

> **面向 AI 代理的工作者：** 使用当前会话内联执行本计划；每项步骤完成后运行对应验证，不覆盖工作区中已有的用户改动。

**目标：** 让“提示词”面板展示最近一次真实发送给 LLM 的完整消息链，同时保留项目附加提示词的编辑入口，并修复管理动作无法被运行时识别的问题。

**架构：** `DecisionStep` 在每次实际调用 LLM 前记录经过 `ContextBudget` 裁剪后的消息；`CharacterRuntime` 保存最近一次快照；`RuntimeManager` 以只读视图返回快照和当前角色附加提示词。前端按消息角色展示完整请求，系统生成内容只读，附加提示词继续通过现有保存动作写入 `data/prompts/<character_id>.md`。

**技术栈：** Python、pytest、React、TypeScript、现有 V3 WebSocket 管理协议、现有蓝灰 CSS token。

---

### 任务 1：为真实提示词快照建立失败测试

**文件：**
- 修改：`tests/test_prompt_overrides.py`
- 修改：`app/runtime/character_turn.py`

- [ ] **步骤 1：编写失败测试**

新增测试验证 `CharacterTurn` 能保存实际发送消息，以及管理处理器返回带有 `available`、`messages`、`character_id` 和 `turn_id` 的提示词视图。

```python
def test_management_handler_exposes_last_prompt_view():
    handler = ManagementHandler()
    handler._manager = _PromptManagerWithView()
    event = asyncio.run(handler.handle("get_prompt_view", {}, "view-1"))[0]
    assert event.payload.data["available"] is True
    assert event.payload.data["messages"][0]["content"] == "系统规则"
```

```python
def test_character_turn_keeps_prompt_messages():
    turn = _turn()
    turn.prompt_messages = [{"role": "system", "content": "系统规则"}]
    assert turn.prompt_messages == [{"role": "system", "content": "系统规则"}]
```

- [ ] **步骤 2：运行测试确认失败**

运行：`D:\conda\envs\qwen3-asr\python.exe -m pytest tests/test_prompt_overrides.py -q`。

预期：因 `_PromptManagerWithView`/`get_prompt_view` 尚不存在而失败；失败原因应是缺少期望行为，不是导入或语法错误。

### 任务 2：记录实际 LLM 请求并提供管理视图

**文件：**
- 修改：`app/runtime/character_turn.py`
- 修改：`app/runtime/steps/decision_step.py`
- 修改：`app/runtime/runtime.py`
- 修改：`app/runtime/management.py`
- 修改：`app/transport/management.py`
- 修改：`tests/test_prompt_overrides.py`

- [ ] **步骤 1：实现最少后端代码**

在 `CharacterTurn` 添加 `prompt_messages`；在 `DecisionStep` 的 LLM 调用包装器和结构化输出修复调用前保存 `deepcopy(messages)`，确保快照与真正传给 provider 的列表一致。`CharacterRuntime` 在 pipeline 完成后保留最近快照，包含 `turn_id`、`character_id`、`messages` 和 `context_budget`。

`RuntimeManager.get_prompt_view()` 返回：

```python
{
    "available": bool(snapshot),
    "character_id": character_id,
    "turn_id": snapshot.get("turn_id", ""),
    "messages": snapshot.get("messages", []),
    "context_budget": snapshot.get("context_budget", {}),
    "override": self._prompt_overrides.get(character_id),
}
```

空快照返回 `available: False` 和空消息数组；`ManagementHandler` 暴露 `get_prompt_view`，并把读取异常转换为 `ManagementFailure`，避免 WebSocket 请求被未捕获异常中断。

- [ ] **步骤 2：运行定向测试确认通过**

运行：`D:\conda\envs\qwen3-asr\python.exe -m pytest tests/test_prompt_overrides.py tests/test_decision_components_v3.py -q`。

预期：新增快照测试和既有 planner/management 测试全部通过。

### 任务 3：将前端面板改为完整提示词查看器

**文件：**
- 修改：`frontend/src/ui/PromptPanel.tsx`
- 修改：`frontend/src/styles/index.css`
- 修改：`frontend/src/ui/workspace-state.test.ts`

- [ ] **步骤 1：先补面板行为测试所需的可验证边界**

保持现有抽屉状态测试，并为提示词视图使用的消息数据定义明确的前端类型：消息包含 `role`、`content`，可选 `tool_call_id` 和 `tool_calls`；视图包含 `available`、`messages`、`override` 与上下文预算。

- [ ] **步骤 2：实现面板行为**

面板挂载和每次 `runtime:turn.completed` 后调用 `get_prompt_view`；显示最近请求的时间/轮次信息、消息总数、上下文预算，并按 `system`、`user`、`assistant`、`tool` 角色显示消息卡片。没有快照时显示“尚未捕获 LLM 请求，请先发送一条消息”。

保留一个独立的“项目附加提示词” textarea，读写 `override`，保存仍调用 `set_prompt_override`；不允许编辑或伪造系统快照内容。

- [ ] **步骤 3：统一视觉与交互**

沿用 `DrawerPanel`、Lucide 图标、现有 `--surface`、`--surface-2`、`--line`、`--accent`、`--muted` token；增加消息角色标签、滚动容器、刷新按钮和状态提示，不引入新的主题色或独立布局体系。

- [ ] **步骤 4：运行前端定向验证**

运行：`npm.cmd test`、`npm.cmd run typecheck`。

预期：前端全部测试通过，TypeScript 无错误。

### 任务 4：完整验证与运行态交付检查

**文件：**
- 检查：`git diff --check`
- 检查：`git status --short --untracked-files=all`

- [ ] **步骤 1：运行全量验证**

运行：`D:\conda\envs\qwen3-asr\python.exe -m pytest -q`、`npm.cmd run build`。

- [ ] **步骤 2：检查实际运行服务**

确认重新启动后端/桥接服务后，`get_prompt_view` 不再返回 `unknown_action`；打开面板、发送一条消息、刷新面板，确认展示的消息内容与最近一次真实请求一致。

- [ ] **步骤 3：逐项复核**

确认自定义提示词仍按角色保存；系统提示词只读；快照包含上下文裁剪后的实际消息；现有 `data/pids/processes.json` 改动未被覆盖；没有加入绕过模型安全策略的逻辑。
