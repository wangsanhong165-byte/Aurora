import sqlite3

from app.memory.store import MemoryStore


def test_memory_schema_migration_is_repeatable(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    store._init_db()

    conn = sqlite3.connect(store._db_path)
    version = conn.execute(
        "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
    ).fetchone()[0]
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(logs)").fetchall()
    }

    assert version >= 3
    assert {"turn_id", "write_token"} <= columns


def test_log_turn_is_idempotent_for_character_turn_and_token(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    reply = {"reply_text": "world", "intent": "conversation"}

    first = store.log_turn(
        "hello",
        reply,
        character_id="monika",
        turn_id="turn-1",
        write_token="conversation",
    )
    second = store.log_turn(
        "hello",
        reply,
        character_id="monika",
        turn_id="turn-1",
        write_token="conversation",
    )

    conn = sqlite3.connect(store._db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM logs WHERE character_id = ? AND turn_id = ?",
        ("monika", "turn-1"),
    ).fetchone()[0]

    assert first is True
    assert second is False
    assert count == 2
