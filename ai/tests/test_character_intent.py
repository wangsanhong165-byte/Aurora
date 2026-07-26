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


def test_segment_adapter_preserves_rich_emotion_vad_and_context_tags():
    intent = CharacterIntent.from_llm_segment({
        "emotion": "worried",
        "behavior": "comfort",
        "naturalVAD": {"valence": -0.65, "arousal": 0.7, "dominance": -0.4},
        "contextTags": ["reassuring", " close-up ", "reassuring", 42],
    })
    assert intent.emotion == "worried"
    assert intent.natural_vad == {
        "valence": -0.65, "arousal": 0.7, "dominance": -0.4,
    }
    assert intent.context_tags == ("reassuring", "close-up")
    assert intent.to_dict()["natural_vad"]["arousal"] == 0.7
