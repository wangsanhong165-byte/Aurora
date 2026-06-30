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
        memories = await self.memory.retrieve(query)
        ctx.state["memories"] = memories
