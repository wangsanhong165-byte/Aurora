import asyncio

from app.domain.character import Character
from app.domain.character_self import CharacterSelf
from app.domain.character.mood import MoodTrend
from app.memory.extractor import extract_facts
from app.memory.store import MemoryStore
from app.memory.ticker import MemoryTicker
from app.providers.memory.sqlite_memory import SQLiteMemory
from app.runtime.character_learning import learn_from_turn
from app.runtime.context_assembler import ContextAssembler


class _FactLLM:
    def generate_text(self, **kwargs):
        return (
            '[{"fact":"user likes coffee","type":"preference",'
            '"subject":"user","predicate":"coffee",'
            '"stable_key":"preference:user:coffee",'
            '"confidence":0.9,"importance":0.8}]'
        )


def test_empty_scope_is_not_visible_to_named_character(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    store.upsert_memory(
        memory_type="fact", subject="user", predicate="legacy",
        content="legacy global value", stable_key="fact:user:legacy",
    )
    assert store.list_memories(character_id="monika") == []

    claimed = store.claim_legacy_scope("monika")
    assert claimed["memories"] == 1
    assert store.list_memories(character_id="monika")[0]["content"] == "legacy global value"
    assert store.list_memories(character_id="alice") == []


def test_claim_legacy_scope_merges_duplicate_memory_without_unique_error(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    common = {
        "memory_type": "fact",
        "subject": "user",
        "predicate": "drink",
        "content": "user likes coffee",
        "stable_key": "fact:user:drink",
    }
    store.upsert_memory(**common, importance=0.9)
    store.upsert_memory(**common, character_id="monika", confidence=0.95)

    claimed = store.claim_legacy_scope("monika")

    rows = store.list_memories(
        character_id="monika", active_only=False, limit=10
    )
    assert claimed["memories"] == 1
    assert len(rows) == 1
    assert rows[0]["importance"] == 0.9
    assert rows[0]["confidence"] == 0.95


def test_legacy_fact_dedup_is_character_scoped(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    assert store.add_fact("same fact", character_id="alpha") is True
    assert store.add_fact("same fact", character_id="beta") is True
    assert store.add_fact("same fact", character_id="alpha") is False


def test_extractor_writes_only_canonical_memories(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    stored = extract_facts(
        "a sufficiently long summary", _FactLLM(),
        character_id="monika", store=store,
    )
    assert stored == ["user likes coffee"]
    assert store.fact_count == 0
    assert store.list_memories(character_id="monika")[0]["content"] == "user likes coffee"


def test_extractor_returns_only_candidates_that_pass_normalization(tmp_path):
    class _MixedLLM:
        def generate_text(self, **kwargs):
            return (
                '[{"fact":"valid looking but rejected","confidence":0.1},'
                '{"fact":"second valid memory","confidence":0.9}]'
            )

    store = MemoryStore(base_dir=tmp_path)
    stored = extract_facts(
        "a sufficiently long summary", _MixedLLM(),
        character_id="monika", store=store,
    )

    assert stored == ["second valid memory"]
    assert store.list_memories(character_id="monika")[0]["content"] == "second valid memory"


def test_retrieve_does_not_reinject_raw_logs(tmp_path, monkeypatch):
    store = MemoryStore(base_dir=tmp_path)
    store.log_turn(
        "secret recent line", {"reply_text": "reply"},
        character_id="monika", turn_id="t1", write_token="conversation",
    )
    memory = SQLiteMemory(store=store)
    monkeypatch.setattr(
        "app.memory.compiler.get_prompt_compiled_memory", lambda character_id="": ""
    )
    # A rolling summary exists -> raw logs are NOT re-injected (dedup).
    monkeypatch.setattr(
        "app.memory.compiler.get_conversation_summary",
        lambda character_id="": "近期对话的摘要",
    )
    results = asyncio.run(memory.retrieve("secret", character_id="monika"))
    assert all(item["type"] != "log" for item in results)


def test_retrieve_falls_back_to_logs_without_summary(tmp_path, monkeypatch):
    """Audit P1-9 regression: before the first summary is generated (fresh
    session / right after restart) retrieve falls back to a bounded raw-log
    recall so recent context is not lost."""
    store = MemoryStore(base_dir=tmp_path)
    store.log_turn(
        "secret recent line", {"reply_text": "reply"},
        character_id="monika", turn_id="t1", write_token="conversation",
    )
    memory = SQLiteMemory(store=store)
    monkeypatch.setattr(
        "app.memory.compiler.get_prompt_compiled_memory", lambda character_id="": ""
    )
    monkeypatch.setattr(
        "app.memory.compiler.get_conversation_summary", lambda character_id="": ""
    )
    results = asyncio.run(memory.retrieve("secret", character_id="monika"))
    assert any(item["type"] == "log" for item in results)


def test_ticker_freezes_character_at_notification_time(monkeypatch):
    ticker = MemoryTicker(llm_adapter=_FactLLM())
    scheduled = []
    monkeypatch.setattr(ticker, "_run_background", lambda fn: scheduled.append(fn))
    for _ in range(3):
        ticker.notify_turn("alpha")
    for _ in range(3):
        ticker.notify_turn("beta")
    calls = []
    monkeypatch.setattr(
        "app.memory.ticker.review_turn",
        lambda llm_adapter, character_id="", character_name="", store=None:
            calls.append(character_id) or {"reviewed": True, "stored": []},
    )
    for task in scheduled:
        task()
    assert calls == ["alpha", "beta"]


def test_explicit_preference_replaces_previous_valence(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    character = Character({
        "id": "monika", "name": {"en": "Monika"},
        "character_setting": "persona",
    })
    aggregate = CharacterSelf(character)
    learn_from_turn(character, "我喜欢猫", store, character_self=aggregate)
    learn_from_turn(character, "我不喜欢猫", store, character_self=aggregate)
    assert character.preferences.get("猫").valence < 0
    active = store.list_memories(character_id="monika", memory_type="preference")
    assert len(active) == 1
    assert "不喜欢" in active[0]["content"]


def test_neutral_emotion_decays_long_term_mood_toward_neutral():
    mood = MoodTrend()
    for _ in range(8):
        mood.shift_from_emotion("happy")
    positive = mood.to_dict()["valence"]

    for _ in range(5):
        mood.shift_from_emotion("neutral")

    assert 0 <= mood.to_dict()["valence"] < positive


def test_compiled_memory_uses_one_4000_character_cap():
    compiled, _ = ContextAssembler().assemble_memories([
        {"type": "compiled", "data": {"content": "x" * 5000}},
    ], total_chars=6000)
    assert len(compiled) == 4000


def test_delete_character_data_is_exact_scope(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    for character_id in ("alpha", "beta"):
        store.upsert_memory(
            memory_type="fact", subject="user", predicate="name",
            content=f"{character_id} value", character_id=character_id,
            stable_key="fact:user:name",
        )
        store.log_turn(
            character_id, {"reply_text": "ok"}, character_id=character_id,
            turn_id=character_id, write_token="conversation",
        )
    store.delete_character_data("alpha")
    assert store.list_memories(character_id="alpha") == []
    assert store.recent_turns(5, character_id="alpha") == []
    assert store.list_memories(character_id="beta")
    assert store.recent_turns(5, character_id="beta")
