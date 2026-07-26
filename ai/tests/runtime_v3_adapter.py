"""Test-only adapter for replaying legacy Event fixtures against Runtime V3."""

from app.runtime.character_turn import TurnInput, TurnOrigin
from app.runtime.event import EventType
from app.runtime.runtime import CharacterRuntime


class EventFixtureRuntime(CharacterRuntime):
    async def dispatch_fixture(self, event):
        if event.type == EventType.SPEECH_RECEIVED:
            turn_input = TurnInput(
                audio=event.payload["audio"],
                sample_rate=event.payload.get("sample_rate", 16000),
            )
        elif event.type == EventType.INITIATIVE_TRIGGERED:
            turn_input = TurnInput(
                text=event.payload.get("display_text", event.payload.get("text", "")),
                origin=TurnOrigin.INITIATIVE,
                metadata={"initiative": event.payload.get("initiative", {})},
            )
        else:
            turn_input = TurnInput(text=event.payload.get("text", ""))
        return await self.handle_turn(turn_input)
