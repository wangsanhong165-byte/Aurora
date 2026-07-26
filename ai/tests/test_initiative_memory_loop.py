from app.memory.store import MemoryStore
from app.runtime.initiative_memory import InitiativeMemorySelector


def test_initiative_prefers_open_loop_and_respects_cooldown(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    store.upsert_memory(
        memory_type="open_loop", subject="user", predicate="follow_up",
        content="用户希望下次提醒他继续完成记忆系统",
        character_id="monika", importance=0.9, confidence=0.9,
    )
    selector = InitiativeMemorySelector(store, cooldown_seconds=3600)

    first = selector.select("monika")
    store.mark_initiative_used("monika", first["memory_id"])
    second = selector.select("monika")

    assert first["topic"] == "用户希望下次提醒他继续完成记忆系统"
    assert first["reason"] == "unfinished_topic"
    assert second is None
