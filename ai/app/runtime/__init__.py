"""Canonical runtime exports without eager service or database initialization."""

from app.runtime.character_turn import (
    CharacterTurn,
    PerformancePlan,
    TurnError,
    TurnInput,
    TurnOrigin,
    TurnOutput,
    TurnPhase,
)

__all__ = [
    "CharacterTurn", "TurnInput", "TurnOutput", "TurnOrigin", "TurnPhase",
    "TurnError", "PerformancePlan",
    "Pipeline", "Step",
    "StateStore", "state_store",
    "CharacterRuntime", "runtime",
]


def __getattr__(name: str):
    if name in {"Pipeline", "Step"}:
        from app.runtime.pipeline import Pipeline, Step
        return {"Pipeline": Pipeline, "Step": Step}[name]
    if name in {"StateStore", "state_store"}:
        from app.runtime.state_store import StateStore, state_store
        return {"StateStore": StateStore, "state_store": state_store}[name]
    if name in {"CharacterRuntime", "runtime"}:
        from app.runtime.runtime import CharacterRuntime, runtime
        return {"CharacterRuntime": CharacterRuntime, "runtime": runtime}[name]
    raise AttributeError(name)
