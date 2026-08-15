import pytest

from app.domain.character.persona import Persona
from app.domain.character import Character
from app.domain.character.personality_profile import (
    PersonalityProfile,
    normalize_personality_profile,
)


def test_structured_personality_is_normalized_and_rendered_as_stable_identity():
    raw = {
        "values": ["真诚", "真诚", "尊重边界"],
        "motivations": ["陪伴用户完成长期目标"],
        "speech_style": {
            "tone": ["自然", "不端着"],
            "habits": ["句子长短交替"],
            "avoid": ["复述系统状态"],
        },
        "self_preferences": {
            "likes": ["安静的夜晚"],
            "dislikes": ["被当作工具"],
        },
        "relationship_style": {
            "new": "克制而友好",
            "familiar": "会自然地开玩笑",
            "close": "坦率但不越界",
        },
        "boundaries": ["不伪造已经发生的动作"],
    }

    profile = PersonalityProfile.from_value(raw)

    assert profile.to_dict()["values"] == ["真诚", "尊重边界"]
    prompt = profile.to_prompt()
    assert "角色自己的喜好" in prompt
    assert "安静的夜晚" in prompt
    assert "用户喜好" not in prompt
    assert "新关系：克制而友好" in prompt


def test_persona_keeps_legacy_setting_and_appends_optional_profile():
    persona = Persona({
        "id": "alice",
        "name": {"zh": "爱丽丝"},
        "character_setting": "保持自然。",
        "personality_profile": {"values": ["诚实"]},
    })

    assert persona.setting == "保持自然。"
    assert "保持自然。" in persona.prompt_context
    assert "诚实" in persona.prompt_context


def test_invalid_personality_profile_is_rejected_at_write_boundary():
    with pytest.raises(ValueError, match="personality_profile"):
        normalize_personality_profile(["not", "an", "object"])


def test_prompt_compiler_includes_stable_profile_without_mixing_dynamic_state():
    from app.runtime.character_turn import CharacterTurn, TurnInput
    from app.runtime.prompt_compiler import PromptCompiler

    character = Character({
        "id": "alice", "name": {"zh": "爱丽丝"},
        "character_setting": "保持自然。",
        "personality_profile": {
            "values": ["诚实"],
            "self_preferences": {"likes": ["安静的夜晚"]},
        },
    })
    turn = CharacterTurn(input=TurnInput(text="你好"))
    turn.character = character

    compiled = PromptCompiler().compile(turn, None)
    persona_message = next(
        item for item in compiled.messages if item.get("_source_id") == "persona"
    )

    assert "诚实" in persona_message["content"]
    assert "角色自己的喜好" in persona_message["content"]
    assert "relationship affinity" not in persona_message["content"]
