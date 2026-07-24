from app.runtime.pipeline import Step
from app.runtime.context import Context
from app.interfaces.memory import MemoryInterface


class MemoryRetrieveStep(Step):
    """Retrieve relevant memory context for the current event."""

    def __init__(self, memory: MemoryInterface):
        self.memory = memory

    async def run(self, ctx: Context) -> None:
        query = ctx.user_text or ctx.event.payload.get("text", "")
        if not query:
            return
        character = ctx.state.get("character")
        char_id = getattr(character, "id", "") if character is not None else ""
        memories = await self.memory.retrieve(
            query,
            character_id=char_id or "",
            event_type=ctx.event.type,
            input_origin=ctx.input_origin,
        )
        ctx.state["memories"] = memories
