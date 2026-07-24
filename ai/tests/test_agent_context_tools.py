import asyncio

from app.core.initiative_queue import InitiativeEvent
from app.core.intent import compute_candidates
from app.domain.character import Character
from app.runtime.context import Context
from app.runtime.event import Event, EventType
from app.runtime.steps.character_step import CharacterStep
from app.runtime.steps.memory_retrieve_step import MemoryRetrieveStep
from app.runtime.steps.memory_save_step import MemorySaveStep


def run(coro):
    return asyncio.run(coro)


def test_reminder_candidate_preserves_task_payload():
    event = InitiativeEvent(
        type="reminder",
        payload={"task_name": "喝水", "task_id": "water"},
        priority=3,
    )
    candidate = max(compute_candidates(0, 50, events=[event]), key=lambda item: item["score"])
    assert candidate["type"] == "scheduled_reminder"
    assert candidate["topic"] == "喝水"
    assert candidate["source_payload"]["task_id"] == "water"


class RecordingMemory:
    def __init__(self):
        self.retrieve_call = None
        self.stored = []

    async def retrieve(self, query, limit=10, **context):
        self.retrieve_call = (query, limit, context)
        return []

    async def store(self, event_type, data):
        self.stored.append((event_type, data))

    async def consolidate(self):
        return None


def test_memory_retrieval_passes_character_and_origin_without_query_prefix():
    memory = RecordingMemory()
    ctx = Context(Event(EventType.INITIATIVE_TRIGGERED, {"display_text": "提醒喝水"}))
    ctx.user_text = "提醒喝水"
    ctx.input_origin = "initiative"
    ctx.state["character"] = Character({
        "id": "monika", "name": {"en": "Monika"}, "character_setting": "Be natural."
    })

    run(MemoryRetrieveStep(memory).run(ctx))

    query, _, metadata = memory.retrieve_call
    assert query == "提醒喝水"
    assert metadata == {
        "character_id": "monika",
        "event_type": EventType.INITIATIVE_TRIGGERED,
        "input_origin": "initiative",
    }


def test_initiative_save_does_not_persist_prompt_as_user_speech():
    memory = RecordingMemory()
    ctx = Context(Event(EventType.INITIATIVE_TRIGGERED, {
        "display_text": "提醒喝水",
        "initiative": {"intent": "scheduled_reminder", "topic": "喝水"},
    }))
    ctx.user_text = "提醒喝水"
    ctx.reply_text = "该喝水啦。"
    ctx.input_origin = "initiative"

    run(MemorySaveStep(memory).run(ctx))

    _, data = memory.stored[0]
    assert data["user"] == ""
    assert data["assistant"] == "该喝水啦。"
    assert data["origin"] == "initiative"
    assert data["initiative"]["topic"] == "喝水"


def test_character_step_can_switch_active_character():
    old = Character({"id": "old", "name": {"en": "Old"}, "character_setting": "Old"})
    new = Character({"id": "new", "name": {"en": "New"}, "character_setting": "New"})
    step = CharacterStep(old)
    step.set_character(new)
    ctx = Context(Event(EventType.TEXT_RECEIVED, {"text": "hi"}))

    run(step.run(ctx))

    assert ctx.state["character"].id == "new"


def test_tool_policy_blocks_unapproved_initiative_tools():
    from app.runtime.tool_policy import ToolPolicy

    schemas = [
        {"type": "function", "function": {"name": "clock"}, "risk": "read_only",
         "allowed_in_initiative": True},
        {"type": "function", "function": {"name": "delete"}, "risk": "dangerous",
         "allowed_in_initiative": True},
        {"type": "function", "function": {"name": "mystery"}},
    ]
    allowed = ToolPolicy().filter_schemas(schemas, input_origin="initiative")
    assert [s["function"]["name"] for s in allowed] == ["clock"]


def test_response_validator_clamps_and_replaces_invalid_presentation_fields():
    from app.runtime.response_validator import ResponseValidator

    result = ResponseValidator().validate(
        reply="fallback",
        segments=[{
            "text": "hello", "emotion": "not-real", "behavior": "idle",
            "energy": 9, "intensity": -2,
        }],
    )
    assert result.reply == "hello"
    assert result.segments[0]["emotion"] == "neutral"
    assert result.segments[0]["behavior"] == "speak"
    assert result.segments[0]["energy"] == 1.0
    assert result.segments[0]["intensity"] == 0.0


def test_planner_represents_initiative_as_system_event_not_user_message():
    from app.runtime.steps.decision_step import DefaultPlanner

    ctx = Context(Event(EventType.INITIATIVE_TRIGGERED, {"display_text": "提醒喝水"}))
    ctx.user_text = "提醒喝水"
    ctx.input_origin = "initiative"
    ctx.state["initiative"] = {"intent": "scheduled_reminder", "topic": "喝水"}
    ctx.state["character"] = Character({
        "id": "monika", "name": {"en": "Monika"}, "character_setting": "Be natural."
    })
    messages = DefaultPlanner().plan(ctx).messages
    assert not any(m["role"] == "user" for m in messages)
    assert any(
        m["role"] == "system" and "Trusted initiative event" in m["content"]
        for m in messages
    )


def test_malformed_json_reply_is_not_forwarded_as_spoken_text():
    from app.runtime.response_validator import ResponseValidator

    result = ResponseValidator().validate('{"segments": broken}', [])
    assert not result.reply.startswith("{")
    assert result.segments[0]["behavior"] == "speak"


def test_context_assembler_deduplicates_and_bounds_memories():
    from app.runtime.context_assembler import ContextAssembler

    memories = [
        {"type": "fact", "data": {"fact": "likes tea"}},
        {"type": "fact", "data": {"fact": "likes   tea"}},
        {"type": "log", "data": {"role": "user", "content": "x" * 1000}},
    ]
    _, relevant = ContextAssembler().assemble_memories(memories, total_chars=400)
    assert relevant.count("[Fact] likes tea") == 1
    assert sum(map(len, relevant)) <= 400


def test_memory_store_filters_logs_by_character(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "memory.db"))
    from app.memory.store import MemoryStore

    store = MemoryStore(base_dir=tmp_path)
    store.log_turn("same topic alpha", {"reply_text": "A"}, character_id="alpha")
    store.log_turn("same topic beta", {"reply_text": "B"}, character_id="beta")
    alpha = store.search_logs("same topic", limit=10, character_id="alpha")
    assert alpha
    assert {row["character_id"] for row in alpha} == {"alpha"}


def test_memory_store_does_not_create_blank_user_for_initiative(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "initiative.db"))
    from app.memory.store import MemoryStore

    store = MemoryStore(base_dir=tmp_path)
    store.log_turn("", {"reply_text": "主动问候", "intent": "initiative"}, "monika")
    rows = store._get_conn().execute(
        "SELECT role, content FROM logs ORDER BY id"
    ).fetchall()
    assert [(row["role"], row["content"]) for row in rows] == [
        ("assistant", "主动问候")
    ]


def test_observation_event_retains_idle_payload():
    event = InitiativeEvent(
        type="observation", payload={"idle_seconds": 900}, priority=1
    )
    candidates = compute_candidates(900, 50, events=[event])
    observation = next(c for c in candidates if c["type"] == "idle_observation")
    assert observation["source_payload"]["idle_seconds"] == 900


def test_context_assembler_includes_dynamic_character_state():
    from app.runtime.context_assembler import ContextAssembler

    character = Character({
        "id": "monika", "name": {"en": "Monika"}, "character_setting": "Natural."
    })
    character.relationship.update_affinity(0.2)
    character.mood.set("playful")
    character.preferences.update("coding", 0.8)
    character.goals.add("help with the project", priority=5)
    text = ContextAssembler().assemble_character_state(character)
    assert "playful" in text
    assert "coding" in text
    assert "help with the project" in text
    assert "affinity" in text


def test_response_validator_marks_malformed_structured_reply_invalid():
    from app.runtime.response_validator import ResponseValidator

    result = ResponseValidator().validate('{"segments": broken}', [])
    assert result.valid is False


def test_decision_step_retries_malformed_output_once():
    from app.interfaces.llm import LLMResponse
    from app.runtime.steps.decision_step import DecisionStep

    class RepairingLLM:
        def __init__(self):
            self.calls = 0

        async def generate(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(reply='{"segments": broken}')
            return LLMResponse(
                reply="fixed",
                segments=[{"text": "fixed", "emotion": "neutral", "behavior": "speak"}],
            )

    llm = RepairingLLM()
    ctx = Context(Event(EventType.TEXT_RECEIVED, {"text": "hello"}))
    ctx.user_text = "hello"
    run(DecisionStep(llm).run(ctx))
    assert llm.calls == 2
    assert ctx.reply_text == "fixed"


def test_confirmed_tool_executes_and_returns_to_model():
    from app.interfaces.llm import LLMResponse, ToolCall
    from app.runtime.steps.decision_step import DecisionStep

    class ConfirmTool:
        def __init__(self):
            self.executed = False

        async def list_tools(self):
            return [{
                "type": "function",
                "function": {"name": "write_note", "parameters": {"type": "object"}},
                "risk": "confirm",
            }]

        async def execute(self, name, args):
            self.executed = True
            return "written"

    class ToolLLM:
        def __init__(self):
            self.calls = 0

        async def generate(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(tool_calls=[ToolCall("write_note", {"text": "x"})])
            return LLMResponse(reply="done")

    async def approve(name, args, risk):
        return name == "write_note" and risk == "confirm"

    tool = ConfirmTool()
    ctx = Context(Event(EventType.TEXT_RECEIVED, {"text": "write"}))
    ctx.user_text = "write"
    ctx.confirmation_callback = approve
    run(DecisionStep(ToolLLM(), tool_provider=tool).run(ctx))
    assert tool.executed is True
    assert ctx.reply_text == "done"
