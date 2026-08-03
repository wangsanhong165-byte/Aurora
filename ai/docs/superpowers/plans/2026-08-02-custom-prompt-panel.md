# 自定义角色提示词面板实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在左侧功能栏增加“提示词”入口，允许按当前角色编辑并持久化一段合法的项目/角色附加提示词，并确保它进入运行时最终发送给 LLM 的 system 消息。

**架构：** 新增 `PromptOverrideStore` 将内容保存到 `data/prompts/<character_id>.md`；`RuntimeManager` 和 V3 `ManagementHandler` 提供读写动作。`DefaultPlanner` 在角色基础设定之后、记忆和历史之前读取当前角色附加提示词。React 左栏增加 `prompt` section，面板通过现有 `requestCommand` 调用管理动作，样式复用 `DrawerPanel`、蓝灰 CSS token 和现有焦点/按钮规范。

**技术栈：** Python、pytest、React、TypeScript、Vite、lucide-react、现有 CSS variables。

---

### 任务 1：为提示词存储和运行时组装建立失败测试

**文件：**
- 创建：`tests/test_prompt_overrides.py`
- 修改：`frontend/src/ui/workspace-state.test.ts`

- [ ] **步骤 1：编写失败的测试**

测试按角色隔离保存、空内容读取、提示词组装顺序，以及左栏接受 `prompt` section。

```python
def test_prompt_override_is_persisted_per_character(tmp_path):
    store = PromptOverrideStore(tmp_path / "data" / "prompts")
    store.set("monika", "用温和但简洁的语气。")
    assert store.get("monika") == "用温和但简洁的语气。"
    assert store.get("other") == ""

def test_default_planner_places_override_after_character_setting(tmp_path):
    store = PromptOverrideStore(tmp_path / "data" / "prompts")
    store.set("monika", "附加项目规则")
    planner = DefaultPlanner(prompt_store=store)
    messages = planner.plan(character_turn_fixture("monika")).messages
    contents = [m["content"] for m in messages if m["role"] == "system"]
    assert contents.index("附加项目规则") > contents.index("角色基础设定")
```

```ts
test('prompt is a valid drawer section', () => {
  const state = createInitialDrawerState('prompt', 380)
  assert.deepEqual(state, { section: 'prompt', expanded: true, width: 380 })
})
```

- [ ] **步骤 2：运行测试验证失败**

运行：`D:\conda\envs\qwen3-asr\python.exe -m pytest tests/test_prompt_overrides.py -q` 和 `npm.cmd test -- --test-name-pattern="prompt is a valid drawer section"`。

预期：Python 测试因 `PromptOverrideStore`/`DefaultPlanner(prompt_store=...)` 尚不存在而失败，前端测试因 `prompt` 不在 `DrawerSection` 而失败。

### 任务 2：实现存储、管理动作和运行时组装

**文件：**
- 创建：`app/runtime/prompt_overrides.py`
- 修改：`app/runtime/management.py`
- 修改：`app/transport/management.py`
- 修改：`app/runtime/default_planner.py`
- 测试：`tests/test_prompt_overrides.py`

- [ ] **步骤 1：实现最少代码让存储和组装测试通过**

`PromptOverrideStore` 只负责按字符 ID 读写 Markdown 文件，写入使用临时文件替换；空文本保存为空内容；限制单条提示词为 12000 字符。

`RuntimeManager` 提供 `get_prompt_override()` 和 `set_prompt_override(content)`，按运行时当前角色 ID 调用存储；`ManagementHandler` 暴露 `get_prompt_override`、`set_prompt_override` 两个动作。

`DefaultPlanner` 接收可选 `prompt_store`，默认使用项目 `data/prompts`，在角色 `persona.setting` 后追加非空 override。

- [ ] **步骤 2：运行后端测试验证通过**

运行：`D:\conda\envs\qwen3-asr\python.exe -m pytest tests/test_prompt_overrides.py -q tests/test_decision_components_v3.py -q`。

预期：新增测试及已有 prompt compiler 测试通过。

### 任务 3：增加左侧入口和提示词编辑面板

**文件：**
- 创建：`frontend/src/ui/PromptPanel.tsx`
- 修改：`frontend/src/ui/workspace-state.ts`
- 修改：`frontend/src/ui/CompanionWorkspace.tsx`
- 修改：`frontend/src/styles/index.css`

- [ ] **步骤 1：实现面板行为**

面板挂载时调用 `get_prompt_override`；textarea 只编辑本地 draft；保存时调用 `set_prompt_override`，显示保存状态和错误状态；保存成功后保留内容并显示当前角色范围说明。

- [ ] **步骤 2：实现统一视觉**

使用 `DrawerPanel title="提示词"`、`FilePenLine` 图标、现有 `--surface`/`--surface-2`/`--line`/`--accent`/`--muted` token、现有 300–520px 抽屉宽度和全局焦点环；不新增独立深色主题或内联颜色体系。

- [ ] **步骤 3：运行前端测试**

运行：`npm.cmd test -- --test-name-pattern="prompt|drawer"`。

预期：workspace 状态测试通过，现有抽屉状态测试不回归。

### 任务 4：完整验证和交付检查

**文件：**
- 检查：`git diff --check`
- 检查：`git status --short`

- [ ] **步骤 1：运行 Python 定向测试**

运行：`D:\conda\envs\qwen3-asr\python.exe -m pytest tests/test_prompt_overrides.py tests/test_decision_components_v3.py -q`。

- [ ] **步骤 2：运行前端类型检查、构建和测试**

运行：`npm.cmd run typecheck`、`npm.cmd run build`、`npm.cmd test`。

- [ ] **步骤 3：逐项复核**

确认：左栏有提示词入口；面板保存后重开仍能读取；不同角色内容隔离；`DefaultPlanner` 生成的 system 消息包含该内容；现有 `data/pids/processes.json` 改动未被覆盖；没有引入绕过模型安全策略的专用逻辑。
