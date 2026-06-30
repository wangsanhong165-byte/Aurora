from app.runtime.pipeline import Step
from app.runtime.context import Context
from app.runtime.event import EventType
from app.interfaces.asr import ASRInterface


class ASRStep(Step):
    """Transcribe speech audio to text."""

    def __init__(self, asr_provider: ASRInterface):
        self.asr = asr_provider

    async def run(self, ctx: Context) -> None:
        if ctx.event.type == EventType.SPEECH_RECEIVED:
            audio = ctx.event.payload.get("audio", b"")
            ctx.user_text = await self.asr.transcribe(audio)
