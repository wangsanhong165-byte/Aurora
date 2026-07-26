from app.memory.store import MemoryStore


def test_memory_can_be_edited_and_safely_forgotten(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    memory_id = store.upsert_memory(
        memory_type="preference", subject="user", predicate="likes",
        content="likes tea", character_id="monika",
    )
    updated = store.update_memory(
        memory_id, character_id="monika", content="likes green tea",
        importance=0.9, confidence=0.95,
    )
    assert updated["content"] == "likes green tea"
    assert updated["importance"] == 0.9
    assert store.forget_memory(memory_id, character_id="other") is False
    assert store.forget_memory(memory_id, character_id="monika") is True
    assert store.list_memories(character_id="monika") == []
    assert store.list_memories(
        character_id="monika", active_only=False
    )[0]["active"] == 0
