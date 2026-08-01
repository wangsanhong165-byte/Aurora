from app.interfaces.llm import LLMResponse
from app.runtime.character_turn import CharacterTurn, TurnInput
from app.runtime.prompt_compiler import PromptCompiler
from app.runtime.response_interpreter import ResponseInterpreter


class _Planner:
    def plan(self, turn):
        return type("Plan", (), {"messages": [{"role": "user", "content": turn.user_text}]})()


def test_prompt_compiler_returns_detached_messages_without_mutating_turn():
    turn = CharacterTurn(input=TurnInput(text="hello"))
    compiler = PromptCompiler(planner=_Planner())

    request = compiler.compile(turn, character_self=None)
    request.messages[0]["content"] = "changed"

    assert turn.user_text == "hello"
    assert compiler.compile(turn, None).messages == [
        {"role": "user", "content": "hello"}
    ]


def test_response_interpreter_produces_semantic_performance_only():
    turn = CharacterTurn(input=TurnInput(text="hello"))
    response = LLMResponse(
        reply="Hi",
        segments=[{
            "text": "Hi",
            "emotion": "happy",
            "behavior": "greet",
            "attention": "user",
            "energy": 0.8,
        }],
    )

    interpreted = ResponseInterpreter().interpret(response, turn)

    assert interpreted.reply_text == "Hi"
    assert interpreted.performance.emotion == "happy"
    assert interpreted.performance.behavior == "greet"
    assert not hasattr(interpreted.performance, "parameter_id")
    assert "Param" not in repr(interpreted.performance)


def test_response_interpreter_rejects_renderer_details():
    turn = CharacterTurn(input=TurnInput(text="hello"))
    response = LLMResponse(
        reply="Hi",
        segments=[{"text": "Hi", "emotion": "happy", "ParamAngleX": 12}],
    )

    interpreted = ResponseInterpreter().interpret(response, turn)

    assert interpreted.warnings == ["renderer_details_removed"]
    assert "ParamAngleX" not in interpreted.segments[0]


def test_response_interpreter_preserves_only_safe_motion_plan():
    turn = CharacterTurn(input=TurnInput(text="hello"))
    response = LLMResponse(
        reply="Hi",
        segments=[{
            "text": "Hi",
            "emotion": "happy",
            "motionPlan": {
                "durationMs": 900,
                "steps": [{
                    "atMs": 0,
                    "durationMs": 600,
                    "primitive": "nod",
                    "intensity": 0.5,
                }],
            },
        }],
    )

    performance = ResponseInterpreter().interpret(response, turn).performance

    assert performance.motion_plan["steps"][0]["primitive"] == "nod"


def test_response_interpreter_selects_dominant_segment_and_keeps_intensity_separate():
    turn = CharacterTurn(input=TurnInput(text="hello"))
    response = LLMResponse(
        reply="Hi",
        segments=[
            {"text": "one", "emotion": "calm", "intensity": 0.6, "energy": 0.9},
            {"text": "two", "emotion": "happy", "intensity": 0.8, "energy": 0.2,
             "attention": "screen"},
            {"text": "three", "emotion": "angry", "intensity": 0.8, "energy": 0.1},
        ],
    )

    performance = ResponseInterpreter().interpret(response, turn).performance

    assert performance.emotion == "happy"
    assert performance.intensity == 0.8
    assert performance.energy == 0.2
    assert performance.attention == "screen"
