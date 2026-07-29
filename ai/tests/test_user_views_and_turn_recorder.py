from pathlib import Path
import asyncio

from app.runtime.character_turn import CharacterTurn, TurnInput
from app.runtime.turn_recorder import TurnRecorder
from app.runtime.user_views import (
    build_capability_view,
    build_character_self_view,
    build_memory_view,
    build_voice_status_view,
)
from app.transport.management import ManagementHandler


def test_character_self_view_is_natural_language_projection():
    view = build_character_self_view(
        {
            "emotion": {"current": "gentle", "intensity": 0.8},
            "mood": {"current": "bright", "valence": 0.9},
            "focus": ["和用户的对话"],
            "goals": ["保持表达一致"],
            "recent_changes": ["记住了用户喜欢安静的界面"],
            "database_id": 42,
            "reasoning": "hidden chain",
        }
    )

    assert view["currentState"] == "现在心情明亮，表达温和，注意力在和用户的对话上。"
    assert view["recentFocus"] == ["和用户的对话"]
    assert view["persistentGoals"] == ["保持表达一致"]
    assert view["recentChanges"] == ["记住了用户喜欢安静的界面"]
    assert "database_id" not in str(view)
    assert "reasoning" not in str(view)


def test_memory_view_filters_and_hides_technical_fields():
    memories = [
        {
            "id": 8,
            "memory_type": "preference",
            "subject": "user",
            "content": "用户喜欢安静的界面",
            "importance": 0.9,
            "confidence": 0.77,
            "active": 1,
            "updated_at": "2026-07-26T00:00:00+00:00",
            "created_at": "2026-07-20T00:00:00+00:00",
        },
        {
            "id": 9,
            "memory_type": "goal",
            "subject": "character",
            "content": "保持动作与语言一致",
            "importance": 0.5,
            "confidence": 0.6,
            "active": 1,
            "updated_at": "2026-07-25T00:00:00+00:00",
        },
    ]

    view = build_memory_view(memories, query="安静", category="preferences")

    assert view["categories"][0]["id"] == "all"
    assert view["items"] == [{
        "ref": "memory:8",
        "category": "preferences",
        "summary": "用户喜欢安静的界面",
        "updatedAt": "2026-07-26T00:00:00+00:00",
        "formedAt": "2026-07-20T00:00:00+00:00",
        "lastUsedAt": "2026-07-26T00:00:00+00:00",
        "formationReason": "从你表达的偏好中形成",
        "pinned": True,
        "editable": True,
    }]
    assert "confidence" not in str(view)
    assert '"id": 8' not in str(view)


def test_capability_view_exposes_permissions_without_internal_schema():
    view = build_capability_view([
        {
            "name": "read_file",
            "description": "读取用户选择的文件",
            "risk": "confirm",
            "enabled": True,
            "allowed_in_initiative": False,
        }
    ], recent_use={"read_file": "2026-07-26T10:00:00+00:00"})

    assert view["items"][0] == {
        "name": "read_file",
        "description": "读取用户选择的文件",
        "status": "available",
        "permission": "ask",
        "recentlyUsedAt": "2026-07-26T10:00:00+00:00",
        "allowedProactively": False,
    }


def test_voice_view_uses_character_voice_not_provider_class_name():
    runtime = type("Runtime", (), {
        "providers": {"asr": object(), "tts": object()}
    })()
    view = build_voice_status_view(runtime, {
        "name": "Monika",
        "card": {"tts": {"voice": "Monika"}},
    })

    assert view["voice"]["name"] == "Monika"
    assert "object" not in str(view)


def test_turn_recorder_persists_sanitized_read_only_trace(tmp_path: Path):
    recorder = TurnRecorder(tmp_path / "turns.db", max_turns=2, retention_days=30)
    turn = CharacterTurn(input=TurnInput(text="请读取文件"))
    turn.memories = [{
        "type": "memory",
        "data": {"content": "用户喜欢安静", "score": 0.98, "database_id": 12},
    }]
    turn.reply_text = "好的"
    turn.reasoning = "private reasoning"
    turn.output.performance.emotion = "gentle"
    turn.output.performance.behavior = "nod"
    turn.output.performance.attention = "user"
    turn.output.audio = b"RIFFsecret"
    turn.metrics = {"MemoryRetrieveStep_ms": 3.4, "e2e_latency_ms": 9.8}
    turn.learned_memories = [{"content": "用户允许读取该文件", "confidence": 0.8}]
    turn.tool_audit = [{"tool": "read_file", "approved": True, "args": {"path": "C:/secret.txt"}}]

    recorder.record(turn)

    summaries = recorder.list_turns()
    assert summaries[0]["turnId"] == turn.turn_id
    detail = recorder.get_turn(turn.turn_id)
    assert detail["readOnly"] is True
    assert detail["response"]["text"] == "好的"
    assert detail["performance"]["behavior"] == "nod"
    assert detail["memory"]["retrieved"][0]["summary"] == "用户喜欢安静"
    serialized = str(detail)
    assert "private reasoning" not in serialized
    assert "RIFFsecret" not in serialized
    assert "C:/secret.txt" not in serialized
    assert "database_id" not in serialized


def test_turn_recorder_enforces_retention_count(tmp_path: Path):
    recorder = TurnRecorder(tmp_path / "turns.db", max_turns=2)
    turns = [CharacterTurn(input=TurnInput(text=f"turn {index}")) for index in range(3)]
    for index, turn in enumerate(turns):
        turn.created_at += index
        recorder.record(turn)

    assert [item["turnId"] for item in recorder.list_turns()] == [
        turns[2].turn_id,
        turns[1].turn_id,
    ]


def test_management_commands_extend_existing_command_protocol():
    class FakeManager:
        def get_character_self_view(self):
            return {"currentState": "平静"}

        def get_memory_view(self, **kwargs):
            return {"items": [], **kwargs}

        def get_voice_status_view(self):
            return {"microphone": {"status": "ready"}}

        async def get_capability_view(self):
            return {"items": []}

        def get_turns(self, limit):
            return [{"turnId": "turn-1", "limit": limit}]

        def get_turn_detail(self, turn_id):
            return {"turn": {"turnId": turn_id, "readOnly": True}}

        def get_runtime_diagnostics(self):
            return {"readOnly": True}

    handler = ManagementHandler()
    handler._manager = FakeManager()

    response = asyncio.run(handler.handle(
        action="get_turn_detail",
        params={"turn_id": "turn-1"},
        request_id="request-1",
    ))[0]
    assert response.event_type == "management.result"
    assert response.payload.action == "get_turn_detail"
    assert response.payload.data["turn"]["readOnly"] is True


def test_frontend_uses_app_permission_dialog_and_no_frame_replay():
    root = Path(__file__).resolve().parents[1]
    client = (root / "frontend/src/runtime/client.ts").read_text("utf-8")
    workspace = (root / "frontend/src/ui/CompanionWorkspace.tsx").read_text("utf-8")
    developer = (root / "frontend/src/ui/DeveloperWorkspace.tsx").read_text("utf-8")

    assert "window.confirm" not in client
    assert "runtime:permission_requested" in client
    assert "CharacterSelfPanel" in workspace
    assert "MemoryPanel" in workspace
    assert "VoicePanel" in workspace
    assert "CapabilityPanel" in workspace
    assert "DeveloperWorkspace" in workspace
    assert "逐帧参数回放" in developer
    assert "requestAnimationFrame" not in developer
