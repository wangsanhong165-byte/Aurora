"""A2/A3: post-turn self-review + extract-before-destroy.

A2 (reviewer): a light LLM pass over the latest turn writes durable facts
without ever touching the logs table (isolation rule).
A3 (extract_from_turns / forget): durable facts are extracted from logs
about to be deleted before the rows disappear.
"""

import asyncio

from app.memory.store import MemoryStore
from app.memory.reviewer import review_turn
from app.memory.extractor import extract_from_turns
from app.providers.memory.sqlite_memory import SQLiteMemory


class _MockLLM:
    def __init__(self, response):
        self._response = response
        self.calls = 0

    def generate_text(self, **kwargs):
        self.calls += 1
        return self._response


_FACT_JSON = (
    '[{"fact": "用户最近开始学游泳", "type": "fact", "subject": "user", '
    '"predicate": "hobby", "stable_key": "fact:user:hobby", "confidence": 0.9, '
    '"importance": 0.7, "tags": ["游泳"]}]'
)


# ── A2: reviewer ──────────────────────────────────────────────────────────


def test_review_turn_writes_facts_not_logs(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    store.log_turn(
        "用户说他开始学游泳了",
        {"reply_text": "太棒了"},
        character_id="monika", turn_id="t1", write_token="w1",
    )
    llm = _MockLLM(_FACT_JSON)

    result = review_turn(llm, character_id="monika", store=store)

    assert result["reviewed"] is True
    assert result["stored"] == ["用户最近开始学游泳"]
    # The fact landed in the canonical memories table…
    assert store.list_memories(character_id="monika")
    # …but the reviewer's own activity never entered the logs (isolation rule).
    assert len(store.recent_turns(10)) == 2


def test_review_turn_nothing_to_save(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    store.log_turn(
        "嗯嗯", {"reply_text": "好的"}, character_id="monika",
        turn_id="t1", write_token="w1",
    )
    llm = _MockLLM("[]")

    result = review_turn(llm, character_id="monika", store=store)

    assert result["reviewed"] is True
    assert result["stored"] == []
    assert store.search_facts("嗯", character_id="monika") == []


def test_review_turn_skips_too_short_turn(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    llm = _MockLLM(_FACT_JSON)
    result = review_turn(llm, character_id="monika", store=store)
    assert result["reviewed"] is False
    assert llm.calls == 0


def test_ticker_schedules_review_every_3_turns(monkeypatch):
    from app.memory.ticker import MemoryTicker

    class _LLM:
        def generate_text(self, **kw):
            return "[]"

    ticker = MemoryTicker(llm_adapter=_LLM())
    scheduled = []
    monkeypatch.setattr(ticker, "_run_background", lambda fn: scheduled.append(fn))

    for _ in range(9):
        ticker.notify_turn()

    reviews = sum(1 for fn in scheduled if getattr(fn, "__name__", "") == "_on_review")
    assert reviews == 3


def test_ticker_review_throttled(monkeypatch):
    from app.memory.ticker import MemoryTicker

    calls = []

    def fake_review(llm_adapter, character_id="", character_name="", store=None):
        calls.append(1)
        return {"reviewed": True, "stored": []}

    monkeypatch.setattr("app.memory.ticker.review_turn", fake_review)
    ticker = MemoryTicker(llm_adapter=_MockLLM("[]"))
    ticker._on_review()
    ticker._on_review()  # within the 20s throttle window → skipped
    assert len(calls) == 1


# ── A3: extract-before-destroy ────────────────────────────────────────────


def test_extract_from_turns(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    turns = [
        {"role": "user", "content": "我最近开始学游泳了"},
        {"role": "assistant", "content": "很棒，加油！"},
    ]
    llm = _MockLLM(_FACT_JSON)

    stats = extract_from_turns(turns, llm, character_id="monika", store=store)

    assert stats["facts_stored"] == 1
    assert store.list_memories(character_id="monika")


def test_extract_from_turns_skips_empty(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    llm = _MockLLM(_FACT_JSON)
    stats = extract_from_turns([], llm, character_id="monika", store=store)
    assert stats["facts_stored"] == 0
    assert llm.calls == 0


def test_logs_before_returns_oldest_last(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    store.log_turn(
        "第一条", {"reply_text": "一"}, character_id="monika",
        turn_id="t1", write_token="w1",
    )
    store.log_turn(
        "第二条", {"reply_text": "二"}, character_id="monika",
        turn_id="t2", write_token="w2",
    )
    rows = store.logs_before("2099-01-01", limit=10)
    contents = [r["content"] for r in rows]
    assert contents == ["第一条", "一", "第二条", "二"]


def test_forget_extracts_before_delete(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    store.log_turn(
        "用户提到他养了一只猫叫咪咪",
        {"reply_text": "好可爱"},
        character_id="monika", turn_id="t1", write_token="w1",
    )
    # Age the logs so a realistic past cutoff deletes them but not the
    # fact extracted just now (its created_at is "now").
    store._get_conn().execute(
        "UPDATE logs SET created_at = '2023-06-01T00:00:00+00:00'"
    )
    store._get_conn().commit()

    mem = SQLiteMemory(store=store)
    mem._llm_adapter = _MockLLM(
        '[{"fact": "用户养了一只猫", "type": "fact", "subject": "user", '
        '"predicate": "pet", "stable_key": "fact:user:pet", "confidence": 0.9, '
        '"importance": 0.7, "tags": ["猫"]}]'
    )

    count = asyncio.run(mem.forget("2024-01-01"))

    # Durable fact survived the delete (extract ran before destroy)…
    assert any("猫" in f["content"] for f in store.list_memories(character_id="monika"))
    # …while the aged logs were actually removed.
    assert len(store.recent_turns(10)) == 0
    assert count >= 2


def test_forget_without_llm_still_deletes(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    store.log_turn(
        "没有 LLM 也要能删", {"reply_text": "是"},
        character_id="monika", turn_id="t1", write_token="w1",
    )
    mem = SQLiteMemory(store=store)  # no _llm_adapter set
    count = asyncio.run(mem.forget("2099-01-01"))
    assert count >= 2
    assert len(store.recent_turns(10)) == 0
