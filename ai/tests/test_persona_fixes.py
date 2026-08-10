"""P0/P1 persona & memory fixes.

- P0-1: default_planner injects persona.display_name, not the raw name dict.
- P0-2: compiled memory injection cap raised from 1500 to 4000 so the
  longterm section actually reaches the LLM.
- P1-a: compiler._char_name_from_id reads config/characters/ (was characters/).
- P1-c: regex learning ignores pronoun topics (e.g. "我喜欢你" no longer
  stores a bogus "用户喜欢你" preference).
"""

import asyncio
from types import SimpleNamespace

from app.memory.store import MemoryStore
from app.providers.memory.sqlite_memory import SQLiteMemory
from app.domain.character import Character
from app.runtime.character_learning import learn_from_turn
from app.runtime.default_planner import DefaultPlanner
from app.memory import compiler as compiler_mod


# ── P0-1: persona name in the prompt ──────────────────────────────────────


def test_default_planner_uses_display_name():
    char = Character({
        "id": "alice",
        "name": {"zh": "Alice", "en": "Alice"},
        "character_setting": "这是测试设定",
        "reply_language": "zh",
    })
    ctx = SimpleNamespace(
        character=char,
        memories=[],
        conversation=None,
        user_text="你好",
        input_origin="user",
        event=SimpleNamespace(type="user", payload={}),
        initiative=None,
        turn_count=1,
    )
    plan = DefaultPlanner().plan(ctx)
    system_texts = [m["content"] for m in plan.messages if m["role"] == "system"]
    assert any("You are Alice" in t for t in system_texts)
    # The raw dict literal must never reach the prompt.
    assert all("{'zh'" not in t for t in system_texts)
    assert all("Alice" in t for t in system_texts if "You are" in t)


# ── P0-2: compiled memory not truncated at 1500 ───────────────────────────


def test_retrieve_compiled_not_truncated_at_1500(tmp_path, monkeypatch):
    monkeypatch.setattr(compiler_mod, "_get_base", lambda: tmp_path)
    long_md = "## 重要事实\n\n" + ("长段记忆内容" * 400)  # > 3000 chars
    md_dir = tmp_path / "data" / "memory" / "compiled" / "monika"
    md_dir.mkdir(parents=True)
    (md_dir / "memory.md").write_text(long_md, encoding="utf-8")

    store = MemoryStore(base_dir=tmp_path)
    mem = SQLiteMemory(store=store)
    results = asyncio.run(mem.retrieve("咖啡", character_id="monika", limit=5))

    compiled = [r for r in results if r["type"] == "compiled"]
    assert compiled
    assert len(compiled[0]["data"]["content"]) > 1500
    assert compiled[0]["data"]["content"] == long_md[:4000]


# ── P1-a: character name from config/characters/ ──────────────────────────


def test_char_name_from_id_reads_config(tmp_path, monkeypatch):
    monkeypatch.setattr(compiler_mod, "_get_base", lambda: tmp_path)
    char_dir = tmp_path / "config" / "characters" / "testchar"
    char_dir.mkdir(parents=True)
    (char_dir / "character.json").write_text(
        '{"id": "testchar", "name": {"zh": "测试角色"}}', encoding="utf-8"
    )
    assert compiler_mod._char_name_from_id("testchar") == "测试角色"


# ── P1-c: regex learning ignores pronoun topics ───────────────────────────


def test_learn_from_turn_ignores_pronoun_topic(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    char = Character({"id": "alice", "name": {"zh": "Alice"}})

    learned = learn_from_turn(char, "我喜欢你", store)

    assert learned == []
    assert store.list_memories(character_id="alice") == []


def test_learn_from_turn_still_learns_real_topic(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    char = Character({"id": "alice", "name": {"zh": "Alice"}})

    learned = learn_from_turn(char, "我喜欢喝咖啡", store)

    assert any("咖啡" in item["content"] for item in learned)
    rows = store.list_memories(character_id="alice")
    assert any("咖啡" in r["content"] for r in rows)


# ── P1 persona fixes ───────────────────────────────────────────────────────


def test_record_interaction_accumulates_count():
    from app.domain.character import Character
    from app.domain.character_self import CharacterSelf

    char = Character({"id": "monika", "name": {"zh": "Monika"}})
    cs = CharacterSelf(char)
    cs.record_interaction("你好")
    cs.record_interaction("再聊一次")

    snap = cs.snapshot()
    assert snap["interaction_count"] == 2
    assert any("再聊一次" in f for f in snap.get("recent_focus", []))


def test_character_state_liked_excludes_disliked():
    from app.domain.character import Character
    from app.runtime.context_assembler import ContextAssembler

    char = Character({"id": "monika", "name": {"zh": "Monika"}})
    char.preferences.update("猫", 0.8)
    char.preferences.update("下雨", -0.9)

    text = ContextAssembler().assemble_character_state(char)
    # 猫 is liked, 下雨 is disliked and must not appear in the likes line.
    assert "learned likes: 猫" in text
    assert "learned dislikes: 下雨" in text


class _DummyChar:
    class _Rel:
        def to_dict(self):
            return {"affinity": {"default": 0.5}, "interaction_count": {}}

    class _Goals:
        def top(self, n):
            return []

    class _Mood:
        current = "neutral"

    relationship = _Rel()
    goals = _Goals()
    mood = _Mood()


def test_character_state_reads_preferences_from_memories():
    from app.runtime.context_assembler import ContextAssembler

    memories = [
        {"type": "preference", "data": {"content": "用户喜欢咖啡"}, "source": "hybrid"},
        {"type": "preference", "data": {"content": "用户不喜欢香菜"}, "source": "hybrid"},
    ]
    text = ContextAssembler().assemble_character_state(_DummyChar(), memories)
    assert "learned likes: 咖啡" in text
    assert "learned dislikes: 香菜" in text
