"""LLM prompt templates for memory extraction and compilation.

All prompts accept character_name so they adapt to any persona.
Prompts are in Chinese, written from the AI character's first-person perspective.
Following openhanako's design: memory = user profile, not collaboration manual.
"""


def system_rolling_summary(char_name: str = "") -> str:
    name = char_name or "我"
    return f"""你是一个记忆摘要助手。请将最近的对话整理成一段简洁的摘要（2-3句话）。

提炼原则：
- 以 {name} 的第一人称视角写（"{name}今天和用户聊了..."）
- 把同一主题的多次往返归并为一件事，不要逐条流水账
- 优先记录用户是谁、喜欢什么、在意什么、最近关注什么
- 工作相关内容只保留到大主题层级，不写具体细节

可以记录：
- 用户的身份、人格特质、审美、兴趣、喜欢或讨厌的事物
- 用户最近关注的大主题
- 用户生活、创作、关系或长期关注方向的变化

不要记录：
- 不要记录执行步骤、文件名、工具、命令、检查顺序
- 不要记录具体方案、改法、测试或发布流程
- 不要单轮对话内的来回修改、重试

直接输出摘要文本，不要 Markdown 标题，不要 JSON。"""


def system_fact_extraction() -> str:
    return """你是一个记忆拆分器。将以下对话摘要拆分成独立的原子记忆事实。

规则：
1. 只提取用户画像和粗颗粒近况相关的客观事实
   用户画像包括：身份、人格特质、审美、兴趣、喜欢或讨厌的事物、长期关系、长期关注方向
2. 不要提取工作方式偏好、协作流程偏好、工具偏好、文件名、命令、执行细节
3. 每条事实必须是原子的（一条只记一件事）
4. 标签用于后续检索，选择有辨识度的关键词，2~5个
5. 如果摘要中没有值得提取的新内容，返回空数组 []
6. type 只能是 fact、preference、recent_state、episode、relationship、open_loop
7. predicate 表示可被后续事实替换的稳定属性，例如 city、favorite_food、current_project
8. stable_key 使用“type:user:predicate”；同一属性发生变化时必须返回相同 stable_key

输出格式（严格的 JSON 数组，不要 markdown 代码块）：
[
  {"fact": "...", "type": "fact", "subject": "user", "predicate": "...", "stable_key": "fact:user:...", "confidence": 0.8, "importance": 0.7, "tags": ["tag1", "tag2"], "time": null}
]"""


def system_compile_today(char_name: str = "") -> str:
    name = char_name or "我"
    return f"""请把今天的对话摘要整理成一份"今天发生了什么"的简单记录。

以 {name} 的第一人称视角写（"{name}今天..."）。

提炼原则：
- 把同一主题/项目的多次往返归并为一件事
- 时间标注用主时段（"上午/傍晚"），不需精确到分钟
- 优先记录用户是谁、喜欢什么、在意什么
- 工作相关内容只保留到大主题层级

可以记录：
- 用户的身份、人格特质、审美、兴趣
- 用户最近关注的大主题
- 用户生活、创作、关系的变化

不要记录执行细节。

输出3-5条粗颗粒事件，每条1-2句。最多300字。直接输出正文。"""


def system_compile_week(char_name: str = "") -> str:
    name = char_name or "我"
    return f"""请把过去几天的对话摘要整理成一份"本周用户主题概要"。

到这一层，记录已经是粗线条的了。归纳用户这一周大致在关注什么、投入什么、发生了什么重要变化。

以 {name} 的第一人称视角写。

关键定位：
- 持续性的关注主题放最前
- 够分量的个人近况、兴趣变化次之

不要保留：执行步骤、文件名、工具、具体子问题、具体方案。

只记录用户这一周大致关注什么、发生了什么重要变化。直接输出正文，不要 Markdown 标题。"""


def system_compile_longterm() -> str:
    return """请综合之前的长期上下文和本周概要，重写成一份新的长期上下文。

长期上下文的定位是"稳定、跨时间的用户画像"：
- 用户的身份、人格特质、审美、兴趣
- 用户长期喜欢或讨厌的事物
- 长期关注的方向

把新的内容吸收进来，把过期的内容去掉。不要追加，要把新旧内容融合。

输出上限600 tokens。直接输出正文，不要 Markdown 标题。"""


def system_compile_facts() -> str:
    return """请综合现有重要事实和新增候选事实，重写成一份新的重要事实总结。

只保留稳定的、跨时间有效的用户画像：身份、人格特质、审美、兴趣、喜欢或讨厌的事物、长期关系、长期关注方向。

不要保留工作方式、协作流程、工具偏好、执行细节。

输出上限300 tokens。宁可概括合并，也不要堆叠罗列。直接输出正文，不要 Markdown 标题。"""
