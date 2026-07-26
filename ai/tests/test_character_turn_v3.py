import asyncio

import pytest

from app.runtime.character_turn import (
    CharacterTurn,
    TurnError,
    TurnInput,
    TurnOrigin,
    TurnPhase,
)
from app.runtime.runtime import CharacterRuntime


def test_turn_input_requires_exactly_one_primary_payload():
    with pytest.raises(ValueError, match="exactly one"):
        TurnInput()

    with pytest.raises(ValueError, match="exactly one"):
        TurnInput(text="hello", audio=b"wav")


def test_character_turn_has_stable_id_and_valid_phase_transitions():
    turn = CharacterTurn(input=TurnInput(text="hello"))

    assert turn.turn_id
    assert turn.phase is TurnPhase.CREATED

    turn.transition_to(TurnPhase.PROCESSING)
    turn.transition_to(TurnPhase.COMPLETED)

    with pytest.raises(ValueError, match="terminal"):
        turn.transition_to(TurnPhase.PROCESSING)


def test_character_turn_records_structured_error():
    turn = CharacterTurn(input=TurnInput(text="hello"))
    turn.fail("decision.invalid_response", "model output was invalid")

    assert turn.phase is TurnPhase.FAILED
    assert turn.error == TurnError(
        code="decision.invalid_response",
        message="model output was invalid",
        retryable=False,
    )


def test_character_runtime_handle_turn_is_the_only_public_turn_entrypoint():
    runtime = CharacterRuntime()
    turn = asyncio.run(runtime.handle_turn(TurnInput(text="hello")))

    assert isinstance(turn, CharacterTurn)
    assert turn.input.origin is TurnOrigin.USER
    assert turn.phase in {TurnPhase.COMPLETED, TurnPhase.FAILED}
    assert not hasattr(runtime, "dispatch")
    runtime.shutdown()
