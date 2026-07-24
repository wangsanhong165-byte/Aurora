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
