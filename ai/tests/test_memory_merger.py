"""Item 3: LLM merge of near-duplicate memories.

Covers the reconciliation guard (target must still exist), the soft-delete of
absorbed memories, the revive-on-re-extraction semantics, the small-dataset
skip, and per-character isolation.
"""

import json

from app.memory.store import MemoryStore
from app.memory.merger import merge_memories, _group_candidates


class _MockLLM:
    def __init__(self, response):
        self._response = response
        self.calls = 0

    def generate_text(self, **kwargs):
        self.calls += 1
        return self._response


def _seed_memories(store, char, n, predicate="hobby"):
    ids = []
    for i in range(n):
        mid = store.upsert_memory(
            memory_type="fact", subject="user", predicate=predicate,
            content=f"用户喜欢第 {i} 项活动",
            character_id=char, stable_key=f"fact:user:{predicate}:{i}",
        )
        ids.append(mid)
    return ids


def test_merge_skips_small_dataset(tmp_path, monkeypatch):
    store = MemoryStore(base_dir=tmp_path)
    _seed_memories(store, "monika", 5)
    monkeypatch.setattr("app.memory.merger._MIN_MEMORIES_TO_MERGE", 80)
    stats = merge_memories(_MockLLM("{}"), store, character_id="monika")
    assert stats["groups_considered"] == 0
    assert stats["skipped"] == 5


def test_merge_consolidates_group(tmp_path, monkeypatch):
    store = MemoryStore(base_dir=tmp_path)
    ids = _seed_memories(store, "monika", 3, predicate="hobby")
    monkeypatch.setattr("app.memory.merger._MIN_MEMORIES_TO_MERGE", 1)
    response = json.dumps({
        "merge_into": ids[0],
        "obsolete": [ids[1], ids[2]],
        "new_content": "用户喜欢户外活动和游泳",
        "importance": 0.8,
    })
    stats = merge_memories(_MockLLM(response), store, character_id="monika")
    assert stats["merged"] == 1
    assert stats["obsolete"] == 2
    active = store.list_memories(character_id="monika", active_only=True)
    assert len(active) == 1
    assert "户外活动和游泳" in active[0]["content"]
    # Absorbed rows are soft-deleted, not hard-deleted (revivable lifecycle).
    # upsert inserts a new row for the merged content, so the table holds the
    # 3 originals (active=0) plus the 1 new merged row (active=1).
    all_rows = store.list_memories(character_id="monika", active_only=False, limit=100)
    assert len(all_rows) == 4
    assert sum(1 for r in all_rows if r["active"]) == 1


def test_merge_aborts_when_target_missing(tmp_path, monkeypatch):
    store = MemoryStore(base_dir=tmp_path)
    ids = _seed_memories(store, "monika", 3, predicate="hobby")
    monkeypatch.setattr("app.memory.merger._MIN_MEMORIES_TO_MERGE", 1)
    # LLM points at a target that no longer exists.
    response = json.dumps({
        "merge_into": 999999,
        "obsolete": [ids[1], ids[2]],
        "new_content": "合并后的内容",
        "importance": 0.8,
    })
    stats = merge_memories(_MockLLM(response), store, character_id="monika")
    assert stats["merged"] == 0
    assert stats["skipped"] == 1
    # Nothing changed: all three still active.
    assert len(store.list_memories(character_id="monika", active_only=True)) == 3


def test_merge_aborts_when_llm_says_distinct(tmp_path, monkeypatch):
    store = MemoryStore(base_dir=tmp_path)
    _seed_memories(store, "monika", 3, predicate="hobby")
    monkeypatch.setattr("app.memory.merger._MIN_MEMORIES_TO_MERGE", 1)
    stats = merge_memories(_MockLLM('{"merge_into": null}'), store, character_id="monika")
    assert stats["merged"] == 0
    assert len(store.list_memories(character_id="monika", active_only=True)) == 3


def test_merge_is_character_scoped(tmp_path, monkeypatch):
    store = MemoryStore(base_dir=tmp_path)
    a_ids = _seed_memories(store, "alpha", 3, predicate="hobby")
    _seed_memories(store, "beta", 3, predicate="hobby")
    monkeypatch.setattr("app.memory.merger._MIN_MEMORIES_TO_MERGE", 1)
    response = json.dumps({
        "merge_into": a_ids[0],
        "obsolete": [a_ids[1], a_ids[2]],
        "new_content": "alpha 合并结果",
        "importance": 0.8,
    })
    merge_memories(_MockLLM(response), store, character_id="alpha")
    assert len(store.list_memories(character_id="alpha", active_only=True)) == 1
    assert len(store.list_memories(character_id="beta", active_only=True)) == 3


def test_group_candidates_groups_by_predicate(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    _seed_memories(store, "monika", 3, predicate="hobby")
    _seed_memories(store, "monika", 1, predicate="city")
    groups = _group_candidates(store, "monika")
    sizes = sorted(len(g) for g in groups)
    assert sizes == [3]  # only the hobby group has >= 2 members
