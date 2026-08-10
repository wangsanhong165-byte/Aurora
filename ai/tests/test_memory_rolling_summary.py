"""B1 rolling conversation summary tests.

The summary is generated per-character by the extractor, persisted atomically
by the ticker into compiled/{char_id}/conversation_summary.md, injected by
retrieve() as the LAST result, and rendered by ContextAssembler as
"[近期对话] …". default_planner is untouched (no I/O).
"""

import asyncio

import pytest

from app.memory.store import MemoryStore
from app.memory.extractor import run_rolling_summary, run_extraction_pipeline
from app.memory import compiler as compiler_mod
from app.memory.compiler import (
    set_active_char,
    get_active_char_id,
    write_conversation_summary,
    get_conversation_summary,
    clear_conversation_summary,
)
from app.providers.memory.sqlite_memory import SQLiteMemory
from app.runtime.context_assembler import ContextAssembler


class _MockLLM:
    def __init__(self, response):
        self._response = response
        self.calls = 0

    def generate_text(self, **kwargs):
        self.calls += 1
        return self._response


@pytest.fixture
def tmp_compiler(tmp_path, monkeypatch):
    """Point compiler._get_base at tmp_path so files never touch the repo."""
    monkeypatch.setattr(compiler_mod, "_get_base", lambda: tmp_path)
    prev = get_active_char_id()
    set_active_char("monika")
    yield tmp_path
    set_active_char(prev)


def _log(store, text, char, n):
    store.log_turn(text, {"reply_text": "好"}, character_id=char,
                   turn_id=f"t{n}", write_token=f"w{n}")


# ── extractor: character-scoped summary ────────────────────────────────────


def test_run_rolling_summary_is_character_scoped(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    _log(store, "alpha 聊了咖啡", "alpha", 1)
    _log(store, "alpha 又问咖啡的事", "alpha", 2)
    _log(store, "beta 聊了爬山", "beta", 3)
    seen = {}

    class _LLM:
        def generate_text(self, system="", user="", **kw):
            seen["user"] = user
            return "摘要"

    run_rolling_summary(_LLM(), character_id="alpha", store=store)
    assert "alpha" in seen["user"]
    assert "beta" not in seen["user"]


def test_extraction_pipeline_returns_full_summary(tmp_compiler):
    store = MemoryStore(base_dir=tmp_compiler)
    for i in range(3):
        _log(store, f"第{i}轮聊了很详细的内容", "monika", i)
    long_summary = "很长的对话回顾内容" * 30  # >100 chars
    stats = run_extraction_pipeline(
        _MockLLM(long_summary), character_id="monika", store=store
    )
    assert stats["summary"] == long_summary
    assert len(stats["summary"]) > 100


def test_extraction_pipeline_skips_fact_llm_when_summary_watermark_is_unchanged(
    tmp_compiler,
):
    store = MemoryStore(base_dir=tmp_compiler)
    write_conversation_summary("monika", "existing summary", through_log_id=20)
    llm = _MockLLM("must not be called")

    stats = run_extraction_pipeline(
        llm, character_id="monika", store=store
    )

    assert stats["summary"] == "existing summary"
    assert stats["summary_unchanged"] is True
    assert stats["facts_stored"] == 0
    assert llm.calls == 0


def test_rolling_summary_preserves_previous_content_on_llm_failure(tmp_compiler):
    store = MemoryStore(base_dir=tmp_compiler)
    write_conversation_summary("monika", "existing summary", through_log_id=1)
    for index in range(8):
        _log(store, f"new turn {index}", "monika", index + 20)

    summary, through_log_id = run_rolling_summary(
        _MockLLM(""), character_id="monika", store=store, return_record=True
    )

    assert summary == "existing summary"
    assert through_log_id == 1


# ── compiler: atomic per-character persist ────────────────────────────────


def test_write_get_clear_conversation_summary(tmp_compiler):
    write_conversation_summary("monika", "这是摘要内容")
    assert get_conversation_summary("monika") == "这是摘要内容"
    # Empty call returns nothing rather than raising.
    assert get_conversation_summary("nobody") == ""
    clear_conversation_summary("monika")
    assert get_conversation_summary("monika") == ""


def test_compile_today_reassembles_after_stale_section_is_removed(
    tmp_compiler, monkeypatch,
):
    compiled_dir = tmp_compiler / "data" / "memory" / "compiled" / "monika"
    compiled_dir.mkdir(parents=True, exist_ok=True)
    (compiled_dir / "today.md").write_text("stale today", encoding="utf-8")
    (compiled_dir / "memory.md").write_text("stale today", encoding="utf-8")
    monkeypatch.setattr(
        compiler_mod, "memory_store", MemoryStore(base_dir=tmp_compiler)
    )

    compiler_mod.compile_today_and_assemble("monika")

    assert not (compiled_dir / "today.md").exists()
    assert "stale today" not in (compiled_dir / "memory.md").read_text("utf-8")


def test_week_and_longterm_caches_use_source_data_not_their_own_output(
    tmp_compiler, monkeypatch,
):
    store = MemoryStore(base_dir=tmp_compiler)
    _log(store, "one stable conversation", "monika", 1)
    llm = _MockLLM("compiled output")
    monkeypatch.setattr(compiler_mod, "memory_store", store)
    monkeypatch.setattr(compiler_mod, "_llm_adapter_global", llm)

    first_week = compiler_mod.week_digest("monika")
    second_week = compiler_mod.week_digest("monika")
    first_longterm = compiler_mod.longterm_digest("monika", first_week)
    second_longterm = compiler_mod.longterm_digest("monika", second_week)

    assert first_week == second_week == "compiled output"
    assert first_longterm == second_longterm == "compiled output"
    assert llm.calls == 2


def test_conversation_summary_fallback_chain(tmp_compiler):
    write_conversation_summary("monika", "monika 的摘要")
    assert get_conversation_summary("") == "monika 的摘要"  # falls back to active


# ── ticker: persist + stale cleanup ───────────────────────────────────────


def test_ticker_persists_summary(tmp_compiler, monkeypatch):
    from app.memory.ticker import MemoryTicker

    monkeypatch.setattr("app.memory.ticker.memory_store", MemoryStore(base_dir=tmp_compiler))
    monkeypatch.setattr("app.memory.ticker.compile_today_and_assemble", lambda char_id="": None)
    monkeypatch.setattr(
        "app.memory.ticker.run_extraction_pipeline",
        lambda llm_adapter, character_name="", character_id="", store=None:
            {"summary": "滚动摘要内容", "facts_stored": 0},
    )
    ticker = MemoryTicker(llm_adapter=_MockLLM(""))
    ticker._on_turn_threshold()
    assert get_conversation_summary("monika") == "滚动摘要内容"


def test_ticker_clears_stale_summary(tmp_compiler, monkeypatch):
    from app.memory.ticker import MemoryTicker

    write_conversation_summary("monika", "旧摘要")
    monkeypatch.setattr("app.memory.ticker.memory_store", MemoryStore(base_dir=tmp_compiler))
    monkeypatch.setattr("app.memory.ticker.compile_today_and_assemble", lambda char_id="": None)
    monkeypatch.setattr(
        "app.memory.ticker.run_extraction_pipeline",
        lambda llm_adapter, character_name="", character_id="", store=None:
            {"summary": "", "facts_stored": 0},
    )
    ticker = MemoryTicker(llm_adapter=_MockLLM(""))
    ticker._on_turn_threshold()
    assert get_conversation_summary("monika") == ""


def test_ticker_preserves_unchanged_summary(tmp_compiler, monkeypatch):
    from app.memory.ticker import MemoryTicker

    write_conversation_summary("monika", "stable summary", through_log_id=10)
    store = MemoryStore(base_dir=tmp_compiler)
    monkeypatch.setattr("app.memory.ticker.compile_today_and_assemble", lambda char_id="": None)
    monkeypatch.setattr(
        "app.memory.ticker.run_extraction_pipeline",
        lambda llm_adapter, character_name="", character_id="", store=None: {
            "summary": "stable summary",
            "through_log_id": 10,
            "summary_unchanged": True,
            "facts_stored": 0,
        },
    )

    ticker = MemoryTicker(llm_adapter=_MockLLM(""), store=store)
    ticker._on_turn_threshold("monika")

    assert get_conversation_summary("monika") == "stable summary"


# ── retrieve: injected LAST, character-scoped ─────────────────────────────


def test_retrieve_injects_summary_last(tmp_compiler):
    store = MemoryStore(base_dir=tmp_compiler)
    store.add_fact("用户喜欢咖啡", ["咖啡"], character_id="monika")
    write_conversation_summary("monika", "近期聊了很多咖啡")

    mem = SQLiteMemory(store=store)
    results = asyncio.run(mem.retrieve("咖啡", character_id="monika", limit=5))

    types = [r["type"] for r in results]
    assert "conversation_summary" in types
    assert results[-1]["type"] == "conversation_summary"
    assert results[-1]["source"] == "rolling_summary"


def test_retrieve_no_summary_no_entry(tmp_compiler):
    store = MemoryStore(base_dir=tmp_compiler)
    store.add_fact("用户喜欢咖啡", ["咖啡"], character_id="monika")
    mem = SQLiteMemory(store=store)
    results = asyncio.run(mem.retrieve("咖啡", character_id="monika", limit=5))
    assert all(r["type"] != "conversation_summary" for r in results)


# ── ContextAssembler: dedicated branch ────────────────────────────────────


def test_context_assembler_renders_conversation_summary():
    compiled, parts = ContextAssembler().assemble_memories([
        {"type": "conversation_summary",
         "data": {"content": "近期对话的回顾内容"},
         "source": "rolling_summary"},
    ])
    assert compiled == ""
    assert any("[近期对话]" in p and "回顾内容" in p for p in parts)


def test_context_assembler_summary_respects_budget():
    ca = ContextAssembler()
    summary = "回顾" * 600  # > 800 chars after prefix
    compiled, parts = ca.assemble_memories([
        {"type": "conversation_summary", "data": {"content": summary},
         "source": "rolling_summary"},
    ], total_chars=1000)
    rendered = next(p for p in parts if "[近期对话]" in p)
    assert len(rendered) <= 1000
