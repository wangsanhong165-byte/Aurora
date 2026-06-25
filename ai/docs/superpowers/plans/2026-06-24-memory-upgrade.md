# 记忆系统全面升级 实现计划

> **目标：** 基于 openhanako 的设计，对项目的记忆系统进行全面升级：存储层从 JSONL 升级到 SQLite+FTS5，新增后台记忆提取管线（四段编译+turn-based调度），改造 PromptBuilder 读取编译后的记忆。

**架构：** 纯后台异步管线。Storage 层隔离替换，Compilation 管线不阻塞对话，PromptBuilder 只读接口。

**技术栈：** Python + sqlite3（内置）+ FTS5 + LLM 调用（复用现有 adapter）

---

### 任务 1：存储层 — store.py 升级为 SQLite + FTS5

**文件：** 修改 `app/memory/store.py`

保留 MemoryStore 外层接口不变（log_turn, recent_turns, add_fact, search_facts, build_prompt_context），内部实现从 JSONL 替换为 SQLite FTS5。

事实表 schema：id, fact, tags(JSON), time, source, importance, created_at
FTS5 虚拟表用于全文搜索（含 CJK bigram 分字）
搜索策略：标签 json_each 匹配 → FTS5 全文 → LIKE 降级

### 任务 2：记忆提取管线

**文件：** 创建 `app/memory/extractor.py`, `app/memory/prompts.py`

滚动摘要：每 10 轮对话用 LLM 压缩为 2-3 句（Monika 第一人称）
Fact 提取：从摘要中拆分为原子 fact + tags
去重合并：标签重叠度 > 0.55 视为重复

### 任务 3：四段编译管线

**文件：** 创建 `app/memory/compiler.py`

compile_today（300字上限）、compile_week、compile_longterm（600 tokens上限）、compile_facts（300 tokens上限）
assemble() 拼成 memory.md ≤2000 tokens

### 任务 4：调度器

**文件：** 创建 `app/memory/ticker.py`，修改 `app/runtime/turn.py`

notify_turn() → 每10轮触发，notify_session_end() → final摘要
daily_check() → 完整日结

### 任务 5：PromptBuilder 改造

**文件：** 修改 `app/brain/prompt_builder.py`

从 memory.md 读取四段记忆替换旧的 build_prompt_context 调用
