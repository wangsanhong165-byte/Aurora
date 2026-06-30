"""MemorySaveStep — persist conversation turns to memory after reply."""

from app.runtime.pipeline import Step
from app.runtime.context import Context
from app.interfaces.memory import MemoryInterface


class MemorySaveStep(Step):
    """Save the current conversation turn to memory storage.

    Runs after the LLM generates a reply. Stores both the user input
    and the assistant reply as a memory entry.

    Note: Conversation turn-tracking is handled by DecisionStep.
    This step only persists to the memory provider.
    """

    def __init__(self, memory: MemoryInterface):
        self.memory = memory

    async def run(self, ctx: Context) -> None:
        # Get user text from ASR (voice) or event payload (text input)
        user_text = ctx.user_text or ctx.event.payload.get("text", "")
        reply_text = ctx.reply_text or ""

        if not user_text and not reply_text:
            return

        # Store the turn as a memory entry
        await self.memory.store("conversation_turn", {
            "user": user_text,
            "assistant": reply_text,
            "emotion": ctx.emotion,
        })

        # Optionally trigger consolidation every 5 turns
        turn_count = ctx.state.get("turn_count", 0)
        if turn_count > 0 and turn_count % 5 == 0:
            await self.memory.consolidate()
