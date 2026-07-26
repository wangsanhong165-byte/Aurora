from app.memory.store import MemoryStore


def test_hybrid_retrieval_does_not_leak_other_character_facts(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    store.add_fact("Alpha owns a unique blue key", ["key"], character_id="alpha")
    store.add_fact("Beta owns a unique red key", ["key"], character_id="beta")

    alpha = store.search_memories("key", character_id="alpha", limit=10)
    contents = [row["content"] for row in alpha]
    assert any("blue" in content for content in contents)
    assert all("red" not in content for content in contents)
