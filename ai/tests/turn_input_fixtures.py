"""Convert historical regression fixtures into the Runtime V3 input model."""

from app.runtime.character_turn import TurnInput, TurnOrigin
from app.runtime.event import EventType


def turn_input_from_event(event) -> TurnInput:
    if event.type == EventType.SPEECH_RECEIVED:
        return TurnInput(
            audio=event.payload["audio"],
            sample_rate=event.payload.get("sample_rate", 16000),
        )
    if event.type == EventType.INITIATIVE_TRIGGERED:
        return TurnInput(
            text=event.payload.get("display_text", event.payload.get("text", "")),
            origin=TurnOrigin.INITIATIVE,
            metadata={"initiative": event.payload.get("initiative", {})},
        )
    return TurnInput(text=event.payload.get("text", ""))
