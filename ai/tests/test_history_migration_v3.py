import json

from app.memory.history_migration import migrate_legacy_histories
from app.memory.store import MemoryStore


def test_legacy_history_migration_is_lossless_and_idempotent(tmp_path):
    histories = tmp_path / "data" / "memory" / "histories"
    histories.mkdir(parents=True)
    source = histories / "hist_demo.json"
    source.write_text(json.dumps([
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]), encoding="utf-8")
    store = MemoryStore(base_dir=tmp_path)

    first = migrate_legacy_histories(tmp_path, store, character_id="monika")
    second = migrate_legacy_histories(tmp_path, store, character_id="monika")

    assert first == 1
    assert second == 0
    assert source.exists()
    assert (histories / "v2-archive" / "hist_demo.json").exists()
    assert store.history_messages("hist_demo", character_id="monika") == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]
