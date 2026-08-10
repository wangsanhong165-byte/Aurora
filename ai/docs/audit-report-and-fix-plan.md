# Monika 综合审查报告与修复计划

> 日期:2026-08-10
> 方法:六视角并行审查(生命周期/记忆/人格/前端/跨系统/Codex 对抗)+ 17 个 major 发现的独立对抗性验证(23 子代理)。每个结论带 file:line 证据,confirmed 与 plausible 区分,3 个被证伪。
> 基线:后端 534 passed / 30 skipped / 1 failed(唯一失败是工作区既有 Live2D 测试)。

## 一、核心结论

**启动"文本智能异常"的直接根因是系统代理劫持了健康检查**——但注意:对抗性验证证明当前代理转发 loopback 是间歇的(readiness 有时能过),所以它是**状态相关的风险**,不是每次必败。机制确认 + 有真实 ProxyError 日志。

**更严重的是两个 Codex 改动引入的回归**(与代理无关,任何环境下都坏):

1. **Fact 记忆在 prompt 里渲染成空 "[Fact]" 标记**——retrieve 单写 memories 后,混合记忆的 data 只有 `content`,但 [context_assembler.py:60](app/runtime/context_assembler.py:60) 读 `data.get("fact")` → 所有 fact 类型记忆内容全部丢失。
2. **interaction_count 永远是 1、recent_focus/recent_changes 每轮丢失**——[character_self.py:90](app/domain/character_self.py:90) `record_interaction` 从 `character.dynamic_state()` 播种,但 `dynamic_state()` 只返回 5 组状态,不含这 5 个跟踪字段。

## 二、问题清单(按优先级)

### P0 — 必须立即修

| # | 问题 | 证据 | 影响 | 修复 |
|---|---|---|---|---|
| P0-1 | **系统代理劫持 readiness/warmup + 运行时 ASR/TTS 调用** | [health.py:19](app/lifecycle/health.py:19) urllib urlopen 默认读系统代理;[orchestrator.py:235](app/lifecycle/orchestrator.py:235) warmup 同样;[http_adapters.py:20,70](app/models/http_adapters.py:20) requests `trust_env=True`。全仓无 NO_PROXY(soulctl.cjs:196 只继承 process.env)。gsvi_v2.py:25-30 已设 trust_env=False 但兄弟没修。bridge.log 有真实 `ProxyError` + `502 for url: http://127.0.0.1:19203` | readiness 间歇失败 → llm 判异常;运行时 ASR/TTS 合成走代理 → 语音死链 | ① soulctl.cjs:196 子进程 env 加 `NO_PROXY=127.0.0.1,localhost`(electron spawn 258-263 同);② health.py + orchestrator.py 用 `urllib.request.build_opener(ProxyHandler({}))`;③ http_adapters.py 设模块级 session `trust_env=False`(gsvi_v2 同款);④ gsvi.py:56 同修 |
| P0-2 | **Fact 混合记忆渲染空 "[Fact]"**(Codex 引入) | [context_assembler.py:60](app/runtime/context_assembler.py:60) 读 `data.get("fact")`,但 [sqlite_memory.py:199-207](app/providers/memory/sqlite_memory.py:199) 单写 memories 后只发 `data.content` | 所有 fact/preference 类型记忆内容丢失,只留空标记——记忆系统核心输出坏了 | context_assembler.py:61 改读 `data.get("content") or data.get("fact")`;加回归测试(存一条 fact 类型记忆,断言渲染含内容) |

### P1 — 高优先

| # | 问题 | 证据 | 影响 | 修复 |
|---|---|---|---|---|
| P1-1 | **语音服务失败中止整个启动(含纯文本)** | [services.json:53](config/services.json) bridge depends_on [llm,tts,asr] 无 failure_policy;[orchestrator.py:152-156](app/lifecycle/orchestrator.py:152) 依赖缺失即 raise | gsvi/tts 任一失败 → bridge abort → 纯文本聊天也起不来 | bridge 只依赖 llm(文本能力先行),语音异步降级;或给 bridge 设 failure_policy |
| P1-2 | **GSVI readiness 门空操作** | [health.py:26](app/lifecycle/health.py:26) 读 `ready` key,但 GSVI /ready 返回 `status`(api_v2.py:505),`payload.get("ready", True)` 恒 True | 模型未加载也判 ready,tts 提前启动 | probe 兼容 `status=="ready"` 或 GSVI 加 ready 字段 |
| P1-3 | **memories 表无限增长** | [store.py:616](app/memory/store.py:616) 是唯一 `DELETE FROM memories`;upsert 只 deactivate 旧行 | 表无界增长,检索变慢 | _on_daily 定期清理超过保留期的 inactive/archived 行(delete_memories_before) |
| P1-4 | **interaction_count 永远 1 + recent_focus 丢失**(Codex 引入) | [character_self.py:90](app/domain/character_self.py:90) 从 dynamic_state() 播种,但 [character.py:52-59](app/domain/character/character.py:52) dynamic_state 只返回 5 组 | 关系/交互统计失真,前端 user view 空 | record_interaction 改从 `deepcopy(self.snapshot())` 播种再叠 live 状态 |
| P1-5 | **不喜欢的主题列成 "learned likes"** | [context_assembler.py:12](app/runtime/context_assembler.py:12) top_liked 无 valence 过滤,disliked(13-14)有 | prompt 把讨厌的也当喜欢 | liked 加 `if p.valence > 0` 过滤 |
| P1-6 | **两套情绪词汇表** | [character_intent.py:5-10](app/runtime/character_intent.py:5) 接受 love/calm/sleepy 等,[emotion.py](app/domain/character/emotion.py) VALID_EMOTIONS 无这些 | LLM 表达的情绪在持久状态被降级 neutral,Live2D 与状态不一致 | response_interpreter 按 VALID_EMOTIONS 校验/映射,或统一词汇表 |
| P1-7 | **preference 双库漂移** | [character_learning.py:46-48](app/runtime/character_learning.py:46) 双写;前端 update_memory/forget_memory 不同步 PreferenceTracker | 前端删掉的偏好继续被注入 | 前端编辑/遗忘 preference 行时同步 tracker;或 prompt 只从 memories 表读 |
| P1-8 | **非活跃角色 legacy facts 永不 backfill** | [sqlite_memory.py:90-91](app/providers/memory/sqlite_memory.py:90) 只对启动活跃角色 backfill | 非活跃角色的旧 facts 永久不可见 | 启动时遍历 registry.list_ids() 逐角色 backfill |
| P1-9 | **retrieve 丢近期上下文**(Codex 引入) | retrieve 不再注入 search_logs + get_prompt_compiled_memory 丢 today/week | 重启后(内存对话空)、摘要未生成前,近期对话不可召回 | rolling summary 缺失时 fallback `search_logs(limit=5)` |

### P2 — 清理/次要

- **死代码**:`config/.env` 的 `MEMORY_PORT=19204`;docs 仍宣传 19204 memory 服务;stale 测试引用已删的 `app/domain/memory`;`app.memory.on_character_switch`/`CharacterRegistry.on_activate` 死代码(switch 已走 runtime 直接调);store 的 `search_logs`/`search_facts` 死方法;`MoodTrend._MOOD_SCALE`;dead schemas(DEFAULT_MEMORY_PATH/MemoryRecentRequest/MemoryAppendRequest/MemoryResponse)。
- **前端**:Settings→General 的 Character 下拉是死控件(单选项);157 前端测试零覆盖角色管理新面;删除活跃角色在 turn 飞行时可能失败。
- **GSVI 修复后重跑**:gsvi ffmpeg 问题是我验证失误(runtime_config={}),正常启动用 GSVI runtime python,无此问题。

## 三、被对抗性验证证伪的(不修,避免误改)

1. "代理导致 readiness 必定失败" —— **证伪**:当前代理实际转发 loopback,readiness 可过。机制真实但影响是间歇/状态相关。仍应修(NO_PROXY 是防御),但不能当"必败根因"。
2. "claim_legacy_scope 误归属另一个角色" —— **证伪**:空 character_id 池里不存在"另一个角色的数据"(空池只有真正无归属的行),影响不存在。

## 四、修复顺序建议

**阶段一(P0,阻断启动与核心记忆)**
1. P0-1 代理:soulctl.cjs env + health.py/warmup opener + http_adapters.py trust_env=False → 验证 FULL_READY
2. P0-2 Fact 渲染:context_assembler.py 读 content + 回归测试

**阶段二(P1,正确性)**
3. P1-1 bridge 依赖降级(文本先行)
4. P1-2 GSVI readiness 门
5. P1-4 interaction_count 播种修复
6. P1-5 valence 过滤、P1-6 情绪词汇统一
7. P1-7 preference 单一来源、P1-8 backfill 遍历、P1-9 近期上下文 fallback

**阶段三(P1 数据治理 + P2 清理)**
8. P1-3 memories 清理(_on_daily)
9. P2 死代码/死配置清理

每个修复后跑 `uv run python -m pytest -q --basetemp=C:/tmp/pytest-basetemp` 全量回归;前端改动后跑 `frontend` 的 157 测试 + TS 检查 + 构建。

## 五、诚实边界

- 本报告所有 P0/P1 问题都经对抗性验证(confirmed),但"代理间歇性"的严重度标注为**状态相关风险**(机制确认、实际影响视代理转发行为而定)。
- P0-2/P1-4/P1-9 是 Codex 最近改动引入的回归,修复时需保持 Codex 的隔离/单写方向不变。
- 前端部分(P2)未做运行态验证(需浏览器),只做了代码级审查。
