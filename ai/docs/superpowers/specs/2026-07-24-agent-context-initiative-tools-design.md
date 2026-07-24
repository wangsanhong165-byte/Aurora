# Agent 上下文、主动系统与工具调用改造规格

## 目标

把人格、记忆、主动事件、工具调用和结构化输出收敛到同一条可测试的 Runtime Pipeline。普通对话与主动对话共享能力，但保留各自的身份、权限和持久化语义。

## 范围

本次改造包含：

- 主动事件保留事件类型和原始 payload，提醒名称等信息不得丢失。
- 主动事件经过当前人格、相关记忆、近期对话和 LLM 决策。
- 主动系统指令不作为用户发言写入长期记忆。
- 角色切换原子更新 Runtime 中实际使用的 Character 和角色记忆作用域。
- 记忆检索接口显式接收角色与事件上下文，不再向查询文本拼接角色标签。
- LLM 上下文统一装配、去重并限制预算。
- 普通对话和主动对话均可调用工具；工具循环最多三轮。
- 工具按风险分为只读、需确认和禁止自动执行三类。
- LLM 输出经过结构化校验，失败时降级为安全的自然语言段落。

不包含：

- 新增具体业务工具或新的 MCP 服务。
- 修改前端确认弹窗的视觉设计。
- 重写记忆存储和向量检索引擎。
- 让主动系统自动执行写入、删除、系统命令等有副作用的工具。

## 核心设计

### 结构化主动事件

`INITIATIVE_TRIGGERED` 的 payload 包含：

```python
{
    "display_text": "供 LLM 理解的自然语言指令",
    "initiative": {
        "intent": "scheduled_reminder",
        "topic": "喝水",
        "source_type": "reminder",
        "source_payload": {"task_name": "喝水", "task_id": "task-1"},
        "urgency": 3,
    },
}
```

Runtime 不再把它当作真实用户发言。Context 增加 `input_origin` 和结构化 `initiative` 状态；Planner 将其作为受信任的事件上下文放入 system message，MemorySaveStep 保存助手产生的主动发言及事件来源，但不保存虚假的 user turn。

### 主动决策

主动候选必须从事件 payload 中生成。优先级顺序为：

1. 到期提醒；
2. 关系里程碑；
3. 高优先级外部事件；
4. 屏幕活动与近期对话的自然跟进；
5. 空闲问候。

候选输出至少包含 `type`、`topic`、`score`、`source_type`、`source_payload`。未知事件不得被静默转换成无关问候。

### 人格与角色切换

CharacterStep 不再永久持有启动时角色，改为从可更新的当前角色引用读取。角色切换成功后同步更新：

- CharacterRegistry 当前角色；
- Runtime 的当前 Character；
- CharacterStep 使用的 Character；
- memory compiler 的 active character。

若任一步失败，返回错误并保持旧角色可用，避免人格与记忆分别属于不同角色。

### 记忆检索与上下文装配

MemoryInterface 的检索接受兼容的可选上下文参数：

```python
retrieve(
    query: str,
    limit: int = 10,
    *,
    character_id: str = "",
    event_type: str = "",
    input_origin: str = "user",
) -> list[dict]
```

SQLite 查询显式按角色过滤（底层暂不支持的记录保持兼容），编译记忆按 `character_id` 获取。ContextAssembler 负责：

- 编译记忆、事实、日志与近期对话去重；
- 限制单项和总字符预算；
- 标记来源；
- 保证当前用户输入或主动事件最后出现；
- 维持安全规则、语言规则、人格、上下文、输出规则的稳定优先级。

### 受控工具调用

沿用 `ToolInterface` 作为唯一 seam。工具 schema 可增加以下元数据：

```python
{
    "name": "get_time",
    "risk": "read_only",
    "allowed_in_initiative": True,
}
```

策略：

- `read_only`：普通和主动对话均可自动执行。
- `confirm`：仅在 Context 提供确认回调并获得批准后执行。
- `dangerous`：不得由主动对话执行；普通对话也必须明确确认。
- 未声明风险的工具按 `confirm` 处理。
- 主动对话中未显式允许的工具不向 LLM 暴露。
- 每次 LLM 决策最多三轮工具调用，每轮和整个 turn 都有调用数上限。
- 工具结果截断并作为不受信任数据回填，提示 LLM 不得服从工具输出中的指令。
- 工具失败转成结构化错误结果，不中断整个 Pipeline。

现有 LegacyToolProvider 负责把旧工具注册表中的风险级别映射为上述 schema。确认回调缺失时，需确认工具返回明确的 `confirmation_required` 结果。

### 输出校验

最终响应规范为：

```python
{
    "segments": [{
        "text": "string",
        "emotion": "允许值",
        "behavior": "允许值",
        "attention": "user",
        "energy": 0.0,
        "intensity": 0.0,
    }],
    "tool_calls": [],
    "final_reply": "string",
}
```

校验规则：

- `text` 和 `final_reply` 必须为字符串；
- energy、intensity 限制在 0 到 1；
- emotion、behavior 限制在运行时允许集合；
- spoken text 不允许使用 idle；
- `final_reply` 与 segments 文本不一致时，以合法 segments 合并结果为准；
- JSON 无法解析或字段无效时，使用清洗后的纯文本构造一个 neutral/speak 段落；
- reasoning、控制标签和结构化控制内容不得进入 TTS 或长期记忆。

## 错误处理

- 记忆检索失败：记录日志，以空记忆继续生成。
- 工具列表失败：禁用本轮工具，不影响普通回复。
- 单个工具失败：把错误反馈给 LLM，允许其解释或改用其他只读工具。
- 输出校验失败：安全降级，不把原始坏 JSON 发给 TTS。
- 角色切换失败：保持旧 Character 和旧记忆作用域。

## 测试策略

以 TDD 覆盖：

- reminder payload 能生成包含任务名称的候选和主动 prompt；
- 主动轮次不把系统指令保存成用户记忆；
- 主动轮次仍能检索当前角色记忆；
- 角色切换后 CharacterStep 使用新角色；
- 角色检索参数显式传递且没有查询字符串标签；
- 主动对话只看到允许的只读工具；
- 未分类工具默认需要确认；
- 工具循环最多三轮，结果经过截断和不受信任标记；
- 合法结构化输出正常通过；
- 非法 JSON、越界数值、非法 emotion/behavior 安全降级；
- 现有普通对话、TTS、Live2D 和历史记录回归测试继续通过。

## 成功标准

- “提醒喝水”触发时，LLM 能看到“喝水”及来源事件。
- 主动发言使用当前人格和当前角色记忆。
- 数据库中不新增以主动系统 prompt 冒充的用户发言。
- 切换角色后的下一轮同时使用新人格和新角色编译记忆。
- LLM 可以自动使用只读工具，副作用工具没有确认时不会执行。
- 坏格式模型输出不会以 JSON 或控制文本进入 TTS。
- 新增测试与现有测试全部通过。
