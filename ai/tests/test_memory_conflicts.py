"""Regression tests for conflicts found by the A1/A2/A3 adversarial audit.

Covers: character isolation in recent_turns/reviewer/forget, the decay
never-archive loop, stale-state revival on re-confirm, decay skipping
soft-deleted rows, and ticker in-flight coalescing + review/extraction
overlap.
"""

import asyncio
import threading
import time
from datetime import datetime, timezone

from app.memory.store import MemoryStore
from app.memory.reviewer import review_turn
from app.providers.memory.sqlite_memory import SQLiteMemory


class _MockLLM:
    def __init__(self, response):
        self._response = response
        self.calls = 0

    def generate_text(self, **kwargs):
        self.calls += 1
        return self._response


def _days_ago(days: float) -> str:
    return datetime.fromtimestamp(
        time.time() - days * 86400, tz=timezone.utc
    ).isoformat()


_FACT_JSON = (
    '[{"fact": "用户喜欢喝咖啡", "type": "preference", "subject": "user", '
    '"predicate": "favorite_drink", "stable_key": "preference:user:coffee", '
    '"confidence": 0.9, "importance": 0.8, "tags": ["咖啡"]}]'
)


# ── character isolation ───────────────────────────────────────────────────


def test_recent_turns_filters_by_character(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    store.log_turn(
        "alpha 的对话", {"reply_text": "a"}, character_id="alpha",
        turn_id="t1", write_token="w1",
    )
    store.log_turn(
        "beta 的对话", {"reply_text": "b"}, character_id="beta",
        turn_id="t2", write_token="w2",
    )
    alpha = store.recent_turns(2, character_id="alpha")
    assert len(alpha) == 2
    assert "alpha" in alpha[0]["content"]  # the user turn belongs to alpha


def test_reviewer_only_reviews_active_character(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    store.log_turn(
        "alpha 说他喜欢喝咖啡", {"reply_text": "好"}, character_id="alpha",
        turn_id="t1", write_token="w1",
    )
    store.log_turn(
        "beta 说他讨厌下雨", {"reply_text": "嗯"}, character_id="beta",
        turn_id="t2", write_token="w2",
    )
    llm = _MockLLM(_FACT_JSON)

    result = review_turn(llm, character_id="alpha", store=store)

    assert result["reviewed"] is True
    # The canonical memory lands under alpha (whose turns were reviewed)…
    assert any("咖啡" in f["content"] for f in store.list_memories(character_id="alpha"))
    # …and beta's profile is untouched.
    assert store.list_memories(character_id="beta") == []


def test_forget_extracts_per_character(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    store.log_turn(
        "alpha 养猫", {"reply_text": "a"}, character_id="alpha",
        turn_id="t1", write_token="w1",
    )
    store.log_turn(
        "beta 养狗", {"reply_text": "b"}, character_id="beta",
        turn_id="t2", write_token="w2",
    )
    store._get_conn().execute("UPDATE logs SET created_at = '2023-01-01T00:00:00+00:00'")
    store._get_conn().commit()

    mem = SQLiteMemory(store=store)
    mem._llm_adapter = _MockLLM(_FACT_JSON)
    asyncio.run(mem.forget("2024-01-01"))

    # Salvaged facts land under each log row's OWN character.
    assert store.list_memories(character_id="alpha")
    assert store.list_memories(character_id="beta")


# ── decay lifecycle fixes ─────────────────────────────────────────────────


def test_stale_does_not_reset_decay_clock(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    mid = store.upsert_memory(
        memory_type="preference", subject="user", predicate="likes",
        content="40天前的老话题", character_id="monika",
    )
    store._get_conn().execute(
        "UPDATE memories SET last_retrieved_at = NULL, "
        "updated_at = ?, created_at = ? WHERE id = ?",
        (_days_ago(40), _days_ago(60), mid),
    )
    store._get_conn().commit()

    r1 = store.decay_memories()
    assert mid in r1["staled"]

    # Second pass: the stale marking did NOT refresh updated_at, so the row
    # is still mid-window (stale, not yet archived) — not reset to "fresh".
    r2 = store.decay_memories()
    assert mid not in r2["archived"]

    # Push past the archive window and confirm it finally archives.
    store._get_conn().execute(
        "UPDATE memories SET updated_at = ?, created_at = ? WHERE id = ?",
        (_days_ago(95), _days_ago(95), mid),
    )
    store._get_conn().commit()
    r3 = store.decay_memories()
    assert mid in r3["archived"]


def test_never_retrieved_memory_archives_directly(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    mid = store.upsert_memory(
        memory_type="fact", subject="user", predicate="old",
        content="从未被取用的旧事实", character_id="monika",
    )
    store._get_conn().execute(
        "UPDATE memories SET last_retrieved_at = NULL, "
        "updated_at = ?, created_at = ? WHERE id = ?",
        (_days_ago(95), _days_ago(95), mid),
    )
    store._get_conn().commit()
    result = store.decay_memories()
    assert mid in result["archived"]


def test_upsert_reconfirm_clears_stale_state(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    mid = store.upsert_memory(
        memory_type="preference", subject="user", predicate="likes",
        content="喜欢咖啡", character_id="monika",
    )
    store._get_conn().execute(
        "UPDATE memories SET state = 'stale', last_retrieved_at = ?, "
        "updated_at = ? WHERE id = ?",
        (_days_ago(40), _days_ago(40), mid),
    )
    store._get_conn().commit()

    revived = store.upsert_memory(
        memory_type="preference", subject="user", predicate="likes",
        content="喜欢咖啡", character_id="monika",
    )
    assert revived == mid
    row = store.list_memories(character_id="monika", active_only=False)[0]
    assert row["state"] == "active"


def test_decay_skips_soft_deleted_rows(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    mid = store.upsert_memory(
        memory_type="preference", subject="user", predicate="likes",
        content="用户已遗忘的", character_id="monika",
    )
    store.forget_memory(mid, character_id="monika")
    store._get_conn().execute(
        "UPDATE memories SET updated_at = ?, last_retrieved_at = ? WHERE id = ?",
        (_days_ago(95), _days_ago(95), mid),
    )
    store._get_conn().commit()

    result = store.decay_memories()
    assert mid not in result["staled"]
    assert mid not in result["archived"]


# ── ticker lifecycle ──────────────────────────────────────────────────────


def test_ticker_queues_distinct_work_while_coalescing_duplicates():
    from app.memory.ticker import MemoryTicker

    class _LLM:
        def generate_text(self, **kw):
            return "[]"

    ticker = MemoryTicker(llm_adapter=_LLM())
    started = threading.Event()
    release = threading.Event()
    calls = []

    def slow_fn():
        calls.append("start")
        started.set()
        release.wait(2)
        calls.append("end")

    ticker._run_background(slow_fn)
    assert started.wait(2)
    def queued_fn():
        calls.append("queued")

    ticker._run_background(queued_fn)
    ticker._run_background(queued_fn)
    release.set()
    deadline = time.time() + 2
    while "queued" not in calls and time.time() < deadline:
        time.sleep(0.01)

    assert calls.count("queued") == 1
    assert calls.count("start") == 1


def test_ticker_skips_review_on_extraction_turn(monkeypatch):
    from app.memory.ticker import MemoryTicker

    class _LLM:
        def generate_text(self, **kw):
            return "[]"

    ticker = MemoryTicker(llm_adapter=_LLM())
    scheduled = []
    monkeypatch.setattr(ticker, "_run_background", lambda fn: scheduled.append(fn))

    for _ in range(10):
        ticker.notify_turn()

    # Reviews fire on turns 3/6/9; turn 10 (full extraction) skips review.
    reviews = [fn for fn in scheduled if getattr(fn, "__name__", "") == "_on_review"]
    extractions = [
        fn for fn in scheduled if getattr(fn, "__name__", "") == "_on_turn_threshold"
    ]
    assert len(reviews) == 3
    assert len(extractions) == 1
