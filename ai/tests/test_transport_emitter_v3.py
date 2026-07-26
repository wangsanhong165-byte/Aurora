import asyncio

from app.runtime.character_turn import CharacterTurn, TurnInput, TurnPhase
from app.transport.emitter import TransportEmitter
from app.transport.protocol import TextInput
from app.transport.websocket.handler import RuntimeEventHandler


def test_success_lifecycle_has_one_canonical_order():
    turn = CharacterTurn(input=TurnInput(text="hello"))
    turn.transition_to(TurnPhase.PROCESSING)
    turn.reply_text = "world"
    turn.audio = b"wav"
    turn.output.performance.emotion = "happy"
    turn.output.performance.behavior = "greet"
    turn.output.performance.speaking = True
    turn.transition_to(TurnPhase.COMPLETED)

    messages = TransportEmitter().emit(turn)

    assert [message.type for message in messages] == [
        "runtime_status",
        "assistant_message",
        "tts_start",
        "tts_audio",
        "tts_end",
        "character_update",
        "runtime_status",
    ]
    update = messages[-2]
    assert update.behavior == "greet"
    assert not hasattr(update, "model_id")
    assert not hasattr(update, "expression")
    assert not hasattr(update, "motion")


def test_failure_lifecycle_is_error_then_idle():
    turn = CharacterTurn(input=TurnInput(text="hello"))
    turn.fail("decision.invalid", "bad response")

    messages = TransportEmitter().emit(turn)

    assert [message.type for message in messages] == ["error", "runtime_status"]
    assert messages[0].code == "decision.invalid"


def test_websocket_pushes_processing_before_runtime_work_starts():
    pushed = []

    async def push(message):
        pushed.append(message)

    class RuntimeProbe:
        async def handle_turn(self, turn_input, **kwargs):
            assert [message.type for message in pushed] == ["runtime_status"]
            assert pushed[0].state == "processing"
            turn = CharacterTurn(input=turn_input)
            turn.transition_to(TurnPhase.PROCESSING)
            turn.reply_text = "done"
            turn.transition_to(TurnPhase.COMPLETED)
            return turn

    handler = RuntimeEventHandler(runtime=RuntimeProbe(), send_message=push)
    responses = asyncio.run(handler.handle(TextInput(text="hello")))

    assert responses == []
    assert [message.type for message in pushed] == [
        "runtime_status",
        "assistant_message",
        "character_update",
        "runtime_status",
    ]
