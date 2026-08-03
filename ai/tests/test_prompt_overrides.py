import asyncio

from app.domain.character import Character
from app.interfaces.llm import LLMResponse
from app.runtime.character_turn import CharacterTurn, TurnInput
from app.runtime.default_planner import DefaultPlanner
from app.runtime.management import RuntimeManager
from app.runtime.prompt_overrides import PromptOverrideStore
from app.runtime.prompt_config import PromptConfigStore
from app.runtime.steps.decision_step import DecisionStep
from app.transport.management import ManagementHandler


class _Runtime:
    def get_character_info(self):
        return {
            "character_id": "monika",
            "card": {"id": "monika", "name": {"zh": "莫妮卡"}},
        }


class _PromptManager:
    def get_prompt_override(self):
        return {"character_id": "monika", "content": "已保存"}

    def set_prompt_override(self, content):
        return {"character_id": "monika", "content": content}

    def get_prompt_view(self, character_id=""):
        return {
            "available": True,
            "character_id": "monika",
            "turn_id": "turn-1",
            "messages": [{"role": "system", "content": "系统规则"}],
            "context_budget": {"estimated_tokens": 3},
            "override": "附加规则",
        }

    def get_prompt_config(self, character_id=""):
        return {
            "character_id": character_id or "monika",
            "sources": [],
            "addition": "附加规则",
        }

    def set_prompt_config(self, character_id, sources, addition):
        return {
            "character_id": character_id,
            "sources": sources,
            "addition": addition,
        }


class _RecordingLLM:
    def __init__(self):
        self.calls = []

    async def generate(self, messages, **kwargs):
        self.calls.append(messages)
        return LLMResponse(reply="好的")


class _RecordingPlanner:
    def plan(self, turn):
        return type("Plan", (), {
            "messages": [
                {"role": "system", "content": "系统规则"},
                {"role": "user", "content": turn.user_text},
            ]
        })()


def _turn():
    turn = CharacterTurn(input=TurnInput(text="你好"))
    turn.character = Character({
        "id": "monika",
        "name": {"en": "Monika"},
        "character_setting": "角色基础设定",
    })
    return turn


def test_prompt_override_is_persisted_per_character(tmp_path):
    store = PromptOverrideStore(tmp_path / "data" / "prompts")

    store.set("monika", "用温和但简洁的语气。\n")

    assert store.get("monika") == "用温和但简洁的语气。"
    assert store.get("other") == ""


def test_empty_prompt_override_clears_existing_content(tmp_path):
    store = PromptOverrideStore(tmp_path / "data" / "prompts")
    store.set("monika", "旧提示词")

    store.set("monika", "  \n")

    assert store.get("monika") == ""


def test_prompt_source_config_can_replace_disable_and_restore_per_character(tmp_path):
    store = PromptConfigStore(tmp_path / "data" / "prompts")

    saved = store.set("monika", {
        "language": {"mode": "disabled", "content": ""},
        "persona": {"mode": "replace", "content": "新的角色设定"},
    })

    assert saved["language"] == {"mode": "disabled", "content": ""}
    assert saved["persona"] == {"mode": "replace", "content": "新的角色设定"}
    assert store.resolve("monika", "language", "默认语言规则") is None
    assert store.resolve("monika", "persona", "默认角色设定") == "新的角色设定"
    assert store.resolve("other", "persona", "另一角色默认设定") == "另一角色默认设定"

    restored = store.set("monika", {
        "persona": {"mode": "default", "content": "应被清理"},
    })
    assert restored["persona"] == {"mode": "default", "content": ""}
    assert store.resolve("monika", "persona", "默认角色设定") == "默认角色设定"


def test_runtime_manager_reads_and_writes_current_character_prompt(tmp_path):
    manager = RuntimeManager(base_dir=tmp_path, runtime=_Runtime())

    result = manager.set_prompt_override("当前角色的附加设定")

    assert result == {
        "character_id": "monika",
        "content": "当前角色的附加设定",
    }
    assert manager.get_prompt_override() == result


def test_runtime_manager_reads_and_writes_complete_config_for_explicit_character(tmp_path):
    manager = RuntimeManager(base_dir=tmp_path, runtime=_Runtime())

    saved = manager.set_prompt_config(
        "other",
        {
            "persona": {"mode": "replace", "content": "其他角色的设定"},
            "memory_summary": {"mode": "disabled", "content": ""},
        },
        "其他角色的附加内容",
    )
    loaded = manager.get_prompt_config("other")

    assert saved["character_id"] == "other"
    assert loaded["character_id"] == "other"
    assert loaded["addition"] == "其他角色的附加内容"
    persona = next(source for source in loaded["sources"] if source["id"] == "persona")
    memory = next(source for source in loaded["sources"] if source["id"] == "memory_summary")
    assert persona["mode"] == "replace"
    assert persona["content"] == "其他角色的设定"
    assert memory["mode"] == "disabled"
    assert manager.get_prompt_config("monika")["addition"] == ""


def test_prompt_config_exposes_static_defaults_without_a_previous_request(tmp_path):
    runtime = _Runtime()
    runtime._character_step = type("CharacterStep", (), {"character": _turn().character})()
    manager = RuntimeManager(base_dir=tmp_path, runtime=runtime)

    loaded = manager.get_prompt_config("monika")
    language = next(source for source in loaded["sources"] if source["id"] == "language")
    persona = next(source for source in loaded["sources"] if source["id"] == "persona")

    assert language["default_content"].startswith("LANGUAGE LOCK:")
    assert persona["default_content"]
    assert language["last_content"] == ""
    assert persona["last_content"] == ""


def test_management_handler_exposes_prompt_override_actions():
    handler = ManagementHandler()
    handler._manager = _PromptManager()

    loaded = asyncio.run(handler.handle("get_prompt_override", {}, "get-1"))[0]
    saved = asyncio.run(handler.handle(
        "set_prompt_override", {"content": "新设定"}, "set-2"
    ))[0]

    assert loaded.event_type == "management.result"
    assert loaded.payload.data["content"] == "已保存"
    assert saved.payload.data["content"] == "新设定"


def test_management_handler_exposes_character_explicit_prompt_config_actions():
    handler = ManagementHandler()
    handler._manager = _PromptManager()

    loaded = asyncio.run(handler.handle(
        "get_prompt_config", {"character_id": "other"}, "config-get"
    ))[0]
    saved = asyncio.run(handler.handle(
        "set_prompt_config",
        {
            "character_id": "other",
            "sources": {"persona": {"mode": "disabled", "content": ""}},
            "addition": "另一角色规则",
        },
        "config-set",
    ))[0]

    assert loaded.payload.data["character_id"] == "other"
    assert saved.payload.data["character_id"] == "other"
    assert saved.payload.data["addition"] == "另一角色规则"


def test_default_planner_places_override_after_character_setting(tmp_path):
    store = PromptOverrideStore(tmp_path / "data" / "prompts")
    store.set("monika", "附加项目规则")

    messages = DefaultPlanner(prompt_store=store).plan(_turn()).messages
    system_contents = [
        message["content"]
        for message in messages
        if message["role"] == "system"
    ]

    base_index = next(i for i, content in enumerate(system_contents) if "角色基础设定" in content)
    override_index = next(i for i, content in enumerate(system_contents) if "附加项目规则" in content)
    assert override_index > base_index


def test_default_planner_applies_prompt_source_config_to_real_messages(tmp_path):
    override_store = PromptOverrideStore(tmp_path / "data" / "prompts")
    config_store = PromptConfigStore(tmp_path / "data" / "prompts")
    config_store.set("monika", {
        "language": {"mode": "disabled", "content": ""},
        "persona": {"mode": "replace", "content": "只使用新的角色设定"},
    })

    messages = DefaultPlanner(
        prompt_store=override_store,
        prompt_config_store=config_store,
    ).plan(_turn()).messages
    system_contents = [
        message["content"]
        for message in messages
        if message["role"] == "system"
    ]

    assert not any(content.startswith("LANGUAGE LOCK:") for content in system_contents)
    assert "只使用新的角色设定" in system_contents
    assert not any("角色基础设定" in content for content in system_contents)
    assert messages[-1] == {"role": "user", "content": "你好"}


def test_decision_step_records_messages_sent_to_llm():
    llm = _RecordingLLM()
    turn = _turn()

    asyncio.run(DecisionStep(llm, planner=_RecordingPlanner()).run(turn))

    assert turn.prompt_messages == llm.calls[-1]
    assert turn.prompt_messages[0]["content"] == "系统规则"


def test_management_handler_exposes_prompt_view():
    handler = ManagementHandler()
    handler._manager = _PromptManager()

    event = asyncio.run(handler.handle("get_prompt_view", {}, "view-1"))[0]

    assert event.event_type == "management.result"
    assert event.payload.data["available"] is True
    assert event.payload.data["messages"][0]["content"] == "系统规则"


def test_runtime_manager_returns_last_prompt_snapshot_with_override(tmp_path):
    manager = RuntimeManager(base_dir=tmp_path, runtime=_Runtime())
    manager._runtime._last_prompt_snapshot = {
        "turn_id": "turn-1",
        "created_at": 123.0,
        "character_id": "monika",
        "messages": [{"role": "system", "content": "系统规则"}],
        "context_budget": {"estimated_tokens": 3},
    }
    manager.set_prompt_override("附加规则")

    view = manager.get_prompt_view()

    assert view["available"] is True
    assert view["turn_id"] == "turn-1"
    assert view["override"] == "附加规则"
    assert view["context_budget"]["estimated_tokens"] == 3


def test_prompt_view_never_leaks_another_characters_snapshot(tmp_path):
    manager = RuntimeManager(base_dir=tmp_path, runtime=_Runtime())
    manager._runtime._last_prompt_snapshot = {
        "turn_id": "monika-turn",
        "created_at": 123.0,
        "character_id": "monika",
        "messages": [{"role": "system", "content": "Monika 的系统规则"}],
        "context_budget": {"estimated_tokens": 8},
    }

    other_view = manager.get_prompt_view("other")

    assert other_view["character_id"] == "other"
    assert other_view["available"] is False
    assert other_view["messages"] == []
    assert other_view["turn_id"] == ""


def test_prompt_view_keeps_source_identity_after_content_replacement(tmp_path):
    manager = RuntimeManager(base_dir=tmp_path, runtime=_Runtime())
    manager.set_prompt_config(
        "monika",
        {"language": {"mode": "replace", "content": "只用简短英文回答"}},
        "",
    )
    manager._runtime._last_prompt_snapshot = {
        "turn_id": "turn-replaced",
        "created_at": 123.0,
        "character_id": "monika",
        "messages": [
            {"role": "system", "content": "只用简短英文回答"},
            {"role": "user", "content": "你好"},
        ],
        "context_budget": {},
    }

    view = manager.get_prompt_view("monika")

    assert view["messages"][0]["source_id"] == "language"
    assert view["messages"][1]["source_id"] == "user_input"
