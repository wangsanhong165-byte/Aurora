"""A1: memory decay — deterministic lifecycle (active -> stale -> archived).

Pure deterministic transitions, no LLM. Mirrors the Hermes curator
apply_automatic_transitions pattern. Archived rows stay on disk (active=0,
hidden from active_only retrieval) and can be revived by upsert or re-surface.
"""

import sqlite3
import time
from datetime import datetime, timezone

from app.memory.store import (
    MemoryStore,
    _decay_decision,
    STALE_DAYS,
    ARCHIVE_DAYS,
)


def _days_ago(days: float) -> str:
    return datetime.fromtimestamp(
        time.time() - days * 86400, tz=timezone.utc
    ).isoformat()


def _make_store(tmp_path) -> MemoryStore:
    return MemoryStore(base_dir=tmp_path)


def _age(store, memory_id, days: float) -> None:
    """Age a memory's activity timestamps so decay sees it as old."""
    conn = store._get_conn()
    conn.execute(
        "UPDATE memories SET updated_at = ?, last_retrieved_at = ? WHERE id = ?",
        (_days_ago(days), _days_ago(days), memory_id),
    )
    conn.commit()


# ── pure decision function ────────────────────────────────────────────────


def test_decay_decision_thresholds():
    now = time.time()
    base = {
        "state": "active",
        "access_count": 1,
        "last_retrieved_at": _days_ago(1),
        "updated_at": _days_ago(10),
        "created_at": _days_ago(20),
    }

    row = dict(base)
    row["last_retrieved_at"] = _days_ago(STALE_DAYS - 1)
    assert _decay_decision(row, now) is None  # inside the stale window

    row["last_retrieved_at"] = _days_ago(STALE_DAYS + 1)
    assert _decay_decision(row, now) == "stale"

    row["last_retrieved_at"] = _days_ago(ARCHIVE_DAYS + 1)
    assert _decay_decision(row, now) == "archive"

    # archived rows are never re-transitioned
    row["state"] = "archived"
    row["last_retrieved_at"] = _days_ago(ARCHIVE_DAYS + 30)
    assert _decay_decision(row, now) is None


def test_never_used_memory_is_not_decayed_until_window_passes():
    now = time.time()
    row = {
        "state": "active",
        "access_count": 0,
        "last_retrieved_at": "",
        "updated_at": _days_ago(1),
        "created_at": _days_ago(1),
    }
    # Fresh-but-unseen: inside the stale window, never retrieved is fine.
    assert _decay_decision(row, now) is None
    # Once it ages past the window it still decays (reversible, not destructive).
    row["updated_at"] = _days_ago(STALE_DAYS + 1)
    assert _decay_decision(row, now) == "stale"


# ── store-level transitions ───────────────────────────────────────────────


def test_decay_memories_transitions_rows(tmp_path):
    store = _make_store(tmp_path)
    fresh = store.upsert_memory(
        memory_type="preference", subject="user", predicate="likes",
        content="喜欢新鲜的", character_id="monika",
        stable_key="pref:likes:fresh",
    )
    stale = store.upsert_memory(
        memory_type="preference", subject="user", predicate="likes",
        content="喜欢陈旧话题", character_id="monika",
        stable_key="pref:likes:stale",
    )
    archived = store.upsert_memory(
        memory_type="preference", subject="user", predicate="likes",
        content="早已不再提及", character_id="monika",
        stable_key="pref:likes:archived",
    )
    _age(store, stale, STALE_DAYS + 5)
    _age(store, archived, ARCHIVE_DAYS + 5)

    result = store.decay_memories(character_id="monika")

    assert fresh not in result["staled"]
    assert fresh not in result["archived"]
    assert stale in result["staled"]
    assert archived in result["archived"]

    # archived is hidden from active_only retrieval but stays on disk
    active_ids = {r["id"] for r in store.list_memories(character_id="monika")}
    assert fresh in active_ids
    assert stale in active_ids
    assert archived not in active_ids

    archived_row = [
        r for r in store.list_memories(character_id="monika", active_only=False)
        if r["id"] == archived
    ][0]
    assert archived_row["state"] == "archived"
    assert archived_row["active"] == 0


def test_decay_is_character_scoped(tmp_path):
    store = _make_store(tmp_path)
    mid_a = store.upsert_memory(
        memory_type="fact", subject="user", predicate="owns",
        content="alpha 的专属记忆", character_id="alpha",
    )
    mid_b = store.upsert_memory(
        memory_type="fact", subject="user", predicate="owns",
        content="beta 的专属记忆", character_id="beta",
    )
    _age(store, mid_a, STALE_DAYS + 5)

    result = store.decay_memories(character_id="alpha")

    assert mid_a in result["staled"]
    assert mid_b not in result["staled"]
    beta_row = [
        r for r in store.list_memories(character_id="beta", active_only=False)
        if r["id"] == mid_b
    ][0]
    assert beta_row["state"] == "active"


def test_search_bumps_usage_and_reactivates_stale(tmp_path):
    store = _make_store(tmp_path)
    mid = store.upsert_memory(
        memory_type="preference", subject="user", predicate="likes",
        content="喜欢徒步", character_id="monika",
    )
    _age(store, mid, STALE_DAYS + 5)
    store.decay_memories(character_id="monika")
    assert [
        r for r in store.list_memories(character_id="monika", active_only=False)
        if r["id"] == mid
    ][0]["state"] == "stale"

    # Surfacing a stale memory again bumps usage and reactivates it.
    results = store.search_memories("徒步", character_id="monika", limit=5)
    assert any(r["id"] == mid for r in results)

    row = [
        r for r in store.list_memories(character_id="monika", active_only=False)
        if r["id"] == mid
    ][0]
    assert row["access_count"] == 1
    assert row["state"] == "active"
    assert row["last_retrieved_at"]


def test_upsert_revives_archived_memory(tmp_path):
    store = _make_store(tmp_path)
    mid = store.upsert_memory(
        memory_type="preference", subject="user", predicate="likes",
        content="喜欢奶茶", character_id="monika",
    )
    conn = store._get_conn()
    conn.execute(
        "UPDATE memories SET state = 'archived', active = 0 WHERE id = ?", (mid,)
    )
    conn.commit()
    assert store.list_memories(character_id="monika") == []

    # Re-encountering the same fact revives the archived row.
    revived = store.upsert_memory(
        memory_type="preference", subject="user", predicate="likes",
        content="喜欢奶茶", character_id="monika",
    )
    assert revived == mid
    rows = store.list_memories(character_id="monika", active_only=True)
    assert rows[0]["state"] == "active"


def test_consolidate_path_decay_then_rebuild(tmp_path):
    store = _make_store(tmp_path)
    old = store.upsert_memory(
        memory_type="preference", subject="user", predicate="likes",
        content="很久以前喜欢的", character_id="monika",
    )
    _age(store, old, ARCHIVE_DAYS + 5)
    # Same sequence SQLiteMemory.consolidate() now runs.
    result = store.decay_memories()
    store.rebuild_index()
    assert old in result["archived"]


def test_migration_adds_decay_columns(tmp_path):
    """A legacy memories table (no decay columns) gains them on open."""
    db = tmp_path / "data" / "memory" / "memory.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE memories ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "memory_type TEXT NOT NULL,"
        "subject TEXT NOT NULL DEFAULT 'user',"
        "predicate TEXT NOT NULL DEFAULT '',"
        "content TEXT NOT NULL,"
        "character_id TEXT NOT NULL DEFAULT '',"
        "stable_key TEXT NOT NULL,"
        "importance REAL NOT NULL DEFAULT 0.5,"
        "confidence REAL NOT NULL DEFAULT 0.6,"
        "active INTEGER NOT NULL DEFAULT 1,"
        "access_count INTEGER NOT NULL DEFAULT 0,"
        "created_at TEXT NOT NULL,"
        "updated_at TEXT NOT NULL)"
    )
    conn.commit()
    conn.close()

    store = _make_store(tmp_path)
    columns = {
        r[1]
        for r in store._get_conn().execute("PRAGMA table_info(memories)").fetchall()
    }
    assert "last_retrieved_at" in columns
    assert "state" in columns
    # Legacy rows default to active.
    legacy = store.list_memories(active_only=False)
    assert all(r["state"] == "active" for r in legacy)
