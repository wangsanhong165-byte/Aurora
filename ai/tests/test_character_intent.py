from app.runtime.character_intent import CharacterIntent


def test_segment_adapter_accepts_only_high_level_intent_fields():
    intent = CharacterIntent.from_llm_segment({
        "emotion": "happy", "behavior": "greet", "attention": "user",
        "energy": 0.8, "ParamAngleX": 99,
    }, 0.7)
    assert intent.emotion == "happy"
    assert intent.behavior == "greet"
    assert "ParamAngleX" not in intent.to_dict()


def test_segment_adapter_rejects_unknown_intent_values():
    intent = CharacterIntent.from_llm_segment({"emotion": "ParamMouthOpenY", "behavior": "keyframe"})
    assert intent.emotion == "neutral"
    assert intent.behavior == ""


def test_segment_adapter_does_not_restore_removed_v2_fields():
    intent = CharacterIntent.from_llm_segment({
        "tone": "happy",
        "gesture": "wave",
    })
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


def test_segment_adapter_accepts_only_bounded_motion_primitives():
    intent = CharacterIntent.from_llm_segment({
        "emotion": "happy",
        "behavior": "agree",
        "motionPlan": {
            "durationMs": 1400,
            "steps": [
                {
                    "atMs": 0,
                    "durationMs": 700,
                    "primitive": "lean_forward",
                    "intensity": 0.25,
                },
                {
                    "atMs": 350,
                    "durationMs": 650,
                    "primitive": "nod",
                    "intensity": 0.6,
                },
            ],
        },
    })

    assert intent.motion_plan == {
        "durationMs": 1400,
        "steps": [
            {
                "atMs": 0,
                "durationMs": 700,
                "primitive": "lean_forward",
                "intensity": 0.25,
            },
            {
                "atMs": 350,
                "durationMs": 650,
                "primitive": "nod",
                "intensity": 0.6,
            },
        ],
    }


def test_segment_adapter_rejects_motion_plans_with_renderer_fields():
    intent = CharacterIntent.from_llm_segment({
        "motionPlan": {
            "durationMs": 1000,
            "steps": [{
                "atMs": 0,
                "durationMs": 500,
                "primitive": "ParamAngleX",
                "intensity": 1,
                "parameter": "ParamAngleX",
            }],
        },
    })

    assert intent.motion_plan is None


def test_segment_adapter_enforces_llm_gesture_budget():
    intent = CharacterIntent.from_llm_segment({
        "motionPlan": {
            "durationMs": 1800,
            "steps": [
                {"atMs": index * 300, "durationMs": 240, "primitive": "nod", "intensity": 0.4}
                for index in range(4)
            ],
        },
    })

    assert intent.motion_plan is None
