"""P1 memory fixes: retention sweep, retrieve log fallback, per-char backfill."""

import asyncio

import pytest

from app.memory.store import MemoryStore
from app.memory import compiler as compiler_mod
from app.memory.compiler import set_active_char, get_active_char_id
from app.providers.memory.sqlite_memory import SQLiteMemory


@pytest.fixture
def tmp_compiler(tmp_path, monkeypatch):
    monkeypatch.setattr(compiler_mod, "_get_base", lambda: tmp_path)
    prev = get_active_char_id()
    set_active_char("monika")
    yield tmp_path
    set_active_char(prev)


def test_delete_memories_before_only_inactive(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    active_id = store.upsert_memory(
        memory_type="preference", subject="user", predicate="likes",
        content="活跃记忆", character_id="monika",
    )
    old_id = store.upsert_memory(
        memory_type="preference", subject="user", predicate="old",
        content="旧记忆已遗忘", character_id="monika",
    )
    store.forget_memory(old_id, character_id="monika")  # active=0
    store._get_conn().execute(
        "UPDATE memories SET created_at='2023-01-01T00:00:00+00:00' WHERE id=?",
        (old_id,),
    )
    store._get_conn().commit()

    deleted = store.delete_memories_before("2024-01-01", character_id="monika")

    assert deleted == 1
    remaining = store.list_memories(character_id="monika", active_only=False)
    ids = {r["id"] for r in remaining}
    assert active_id in ids
    assert old_id not in ids


def test_delete_memories_before_keeps_active_old(tmp_path):
    """An old but still-active memory is governed by decay, not the sweep."""
    store = MemoryStore(base_dir=tmp_path)
    mid = store.upsert_memory(
        memory_type="fact", subject="user", predicate="x",
        content="老但活跃", character_id="monika",
    )
    store._get_conn().execute(
        "UPDATE memories SET created_at='2020-01-01T00:00:00+00:00' WHERE id=?",
        (mid,),
    )
    store._get_conn().commit()
    assert store.delete_memories_before("2024-01-01", character_id="monika") == 0


def test_retrieve_falls_back_to_logs_without_summary(tmp_compiler):
    store = MemoryStore(base_dir=tmp_compiler)
    store.log_turn(
        "用户昨天聊了咖啡",
        {"reply_text": "好喝"},
        character_id="monika", turn_id="t1", write_token="w1",
    )
    mem = SQLiteMemory(store=store)
    results = asyncio.run(mem.retrieve("咖啡", character_id="monika", limit=5))
    types = [r["type"] for r in results]
    # No rolling summary exists -> bounded raw-log fallback provides recall.
    assert "conversation_summary" not in types
    assert any(r["type"] == "log" and "咖啡" in r["data"]["content"] for r in results)
