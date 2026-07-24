from app.runtime.character_intent import CharacterIntent


def test_segment_adapter_accepts_only_high_level_intent_fields():
    intent = CharacterIntent.from_llm_segment({
        "tone": "happy", "gesture": "greet", "attention": "user",
        "energy": 0.8, "ParamAngleX": 99,
    }, 0.7)
    assert intent.emotion == "happy"
    assert intent.behavior == "greet"
    assert "ParamAngleX" not in intent.to_dict()


def test_segment_adapter_rejects_unknown_intent_values():
    intent = CharacterIntent.from_llm_segment({"emotion": "ParamMouthOpenY", "behavior": "keyframe"})
    assert intent.emotion == "neutral"
    assert intent.behavior == ""
