"""FTS5 CJK retrieval: trigram tokenizer + LIKE fallback.

unicode61 treated a whole CJK run as one token, so no Chinese substring
matched and search_logs had no fallback at all. The fix moves facts_fts /
logs_fts to the trigram tokenizer (>=3 char substrings index) with a LIKE
fallback for 1-2 char queries.
"""

import sqlite3

from app.memory.store import MemoryStore


def _make_store(tmp_path) -> MemoryStore:
    return MemoryStore(base_dir=tmp_path)


def test_cjk_three_char_query_hits_via_trigram(tmp_path):
    store = _make_store(tmp_path)
    store.add_fact("用户最近开始学游泳", ["爱好"], character_id="monika")
    results = store.search_facts("学游泳", character_id="monika")
    assert any("学游泳" in r["fact"] for r in results)


def test_cjk_two_char_query_falls_back_to_like(tmp_path):
    store = _make_store(tmp_path)
    store.add_fact("用户喜欢游泳", ["爱好"], character_id="monika")
    results = store.search_facts("游泳", character_id="monika")
    assert any("游泳" in r["fact"] for r in results)


def test_search_logs_single_char_falls_back_to_like(tmp_path):
    store = _make_store(tmp_path)
    store.log_turn(
        "用户说猫很可爱",
        {"reply_text": "是的"},
        character_id="monika", turn_id="t1", write_token="w1",
    )
    results = store.search_logs("猫", limit=5, character_id="monika")
    assert any("猫很可爱" in r["content"] for r in results)


def test_search_logs_two_char_falls_back_to_like(tmp_path):
    store = _make_store(tmp_path)
    store.log_turn(
        "最近开始学习游泳了",
        {"reply_text": "加油"},
        character_id="monika", turn_id="t1", write_token="w1",
    )
    results = store.search_logs("游泳", limit=5, character_id="monika")
    assert any("游泳" in r["content"] for r in results)


def test_english_trigram_still_works(tmp_path):
    store = _make_store(tmp_path)
    store.log_turn(
        "the quick brown fox",
        {"reply_text": "ok"},
        character_id="monika", turn_id="t1", write_token="w1",
    )
    results = store.search_logs("quick brown", limit=5, character_id="monika")
    assert any("quick brown" in r["content"] for r in results)


def test_legacy_unicode61_fts_migrates_to_trigram(tmp_path):
    db = tmp_path / "data" / "memory" / "memory.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE facts (id INTEGER PRIMARY KEY AUTOINCREMENT, fact TEXT NOT NULL, "
        "tags TEXT NOT NULL DEFAULT '[]', time TEXT, source TEXT DEFAULT '', "
        "importance REAL DEFAULT 0.5, character_id TEXT DEFAULT '', created_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE VIRTUAL TABLE facts_fts USING fts5(fact, tags, content=facts, "
        "content_rowid=id, tokenize='unicode61')"
    )
    conn.execute(
        "INSERT INTO facts(fact, tags, importance, character_id, created_at) "
        "VALUES ('用户最近开始学游泳', '[\"爱好\"]', 0.7, 'monika', "
        "'2026-01-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    store = _make_store(tmp_path)
    # The legacy FTS table was rebuilt as trigram…
    sql = store._get_conn().execute(
        "SELECT sql FROM sqlite_master WHERE name='facts_fts'"
    ).fetchone()[0]
    assert "trigram" in sql
    assert "unicode61" not in sql
    # …and existing rows were re-indexed: a 3-char CJK query now hits.
    results = store.search_facts("学游泳", character_id="monika")
    assert any("学游泳" in r["fact"] for r in results)
