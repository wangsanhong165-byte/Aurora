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
