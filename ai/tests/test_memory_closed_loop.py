import asyncio
import time

from app.memory.store import MemoryStore
from app.runtime.context_assembler import ContextAssembler
from app.memory.lifecycle import store_candidates


def test_structured_memory_upsert_conflicts_and_hybrid_recall(tmp_path):
    store = MemoryStore(base_dir=tmp_path)

    first_id = store.upsert_memory(
        memory_type="preference",
        subject="user",
        predicate="likes",
        content="用户最喜欢草莓蛋糕",
        character_id="monika",
        importance=0.8,
        confidence=0.9,
    )
    second_id = store.upsert_memory(
        memory_type="preference",
        subject="user",
        predicate="likes",
        content="用户现在最喜欢巧克力蛋糕",
        character_id="monika",
        importance=0.9,
        confidence=0.95,
    )
    reactivated_id = store.upsert_memory(
        memory_type="preference",
        subject="user",
        predicate="likes",
        content="用户最喜欢草莓蛋糕",
        character_id="monika",
        importance=0.95,
        confidence=0.98,
    )

    assert first_id != second_id
    assert reactivated_id == first_id
    active = store.list_memories(
        character_id="monika", memory_type="preference", active_only=True
    )
    assert [item["content"] for item in active] == ["用户最喜欢草莓蛋糕"]

    results = store.search_memories("我喜欢吃什么", character_id="monika", limit=5)
    assert results
    assert results[0]["content"] == "用户最喜欢草莓蛋糕"
    assert results[0]["score"] > 0
    assert results[0]["reasons"]


def test_character_state_round_trip(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    state = {
        "relationship": {"affinity": {"default": 0.72}, "interaction_count": {"default": 8}},
        "preferences": {
            "coding": {
                "topic": "coding",
                "valence": 0.8,
                "confidence": 0.7,
                "last_updated": time.time(),
            }
        },
        "goals": {"active": [], "completed": []},
        "mood": {"current": "playful", "valence": 0.3, "history": []},
        "emotion": {"current": "happy", "intensity": 0.6},
    }
    store.save_character_state("monika", state)
    assert store.load_character_state("monika") == state


def test_existing_facts_are_included_in_hybrid_recall(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    assert store.add_fact("用户最近因为修复程序错误而烦躁", ["编程", "情绪"])
    store.claim_legacy_scope("monika")
    store.backfill_legacy_facts(character_id="monika")

    results = store.search_memories("修bug很烦", character_id="monika", limit=5)

    assert any("修复程序错误" in item["content"] for item in results)
    assert any(
        item["content"] == "用户最近因为修复程序错误而烦躁"
        for item in store.list_memories()
    )


def test_structured_hybrid_memory_is_rendered_into_prompt_context():
    compiled, parts = ContextAssembler().assemble_memories([
        {
            "type": "preference",
            "data": {
                "content": "用户喜欢巧克力蛋糕",
                "score": 0.88,
                "reasons": ["semantic_overlap", "important"],
            },
            "source": "hybrid",
        }
    ])
    assert compiled == ""
    assert "用户喜欢巧克力蛋糕" in "\n".join(parts)


def test_unrelated_extracted_facts_do_not_replace_each_other(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    store_candidates(store, [
        {"fact": "用户经常在深夜工作", "tags": ["习惯"]},
        {"fact": "用户正在开发人工智能项目", "tags": ["项目"]},
    ])
    active = store.list_memories()
    assert {item["content"] for item in active} == {
        "用户经常在深夜工作",
        "用户正在开发人工智能项目",
    }


def test_high_value_structured_memory_survives_many_log_results():
    memories = [{
        "type": "preference",
        "data": {"content": "用户喜欢巧克力蛋糕", "score": 0.95},
        "source": "hybrid",
    }]
    memories.extend({
        "type": "log",
        "data": {"role": "user", "content": f"普通旧对话 {i}"},
        "source": "sqlite",
    } for i in range(15))

    _, parts = ContextAssembler().assemble_memories(memories)

    assert any("用户喜欢巧克力蛋糕" in part for part in parts)


def test_new_legacy_facts_are_character_scoped(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    store.add_fact("只属于 Alpha 的秘密", ["秘密"], character_id="alpha")
    store.add_fact("只属于 Beta 的秘密", ["秘密"], character_id="beta")
    alpha = store.search_facts("秘密", character_id="alpha")
    beta = store.search_facts("秘密", character_id="beta")
    assert {item["fact"] for item in alpha} == {"只属于 Alpha 的秘密"}
    assert {item["fact"] for item in beta} == {"只属于 Beta 的秘密"}


def test_legacy_backfill_does_not_restore_edited_or_forgotten_memory(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    original = "用户询问了'赖暴力模型'的问题"
    assert store.add_fact(original)

    store.backfill_legacy_facts()
    memory_id = store.list_memories()[0]["id"]
    updated = store.update_memory(memory_id, content="用户已经修改过的记忆")
    assert updated["content"] == "用户已经修改过的记忆"

    # Simulate the startup migration that runs again after a restart.
    store.backfill_legacy_facts()
    assert [item["content"] for item in store.list_memories()] == [
        "用户已经修改过的记忆"
    ]

    assert store.forget_memory(memory_id)
    store.backfill_legacy_facts()
    assert store.list_memories() == []


def test_hybrid_fact_memory_renders_content_not_empty():
    """Regression: fact-typed hybrid memories must render their content, not
    an empty '[Fact]' marker (retrieve now sends data.content, not data.fact)."""
    compiled, parts = ContextAssembler().assemble_memories([
        {
            "type": "fact",
            "data": {"content": "用户喜欢喝咖啡", "score": 0.9, "reasons": ["important"]},
            "source": "hybrid",
        }
    ])
    assert compiled == ""
    assert any("[Fact]" in p and "用户喜欢喝咖啡" in p for p in parts)
    assert all(p.strip() != "[Fact]" for p in parts)
