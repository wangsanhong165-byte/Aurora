"""HistorySaveStep — persist conversation turns to file-based history.

Saves each user+assistant exchange to the RuntimeManager's history store
so the frontend HistoryPanel can list and reload past conversations.
"""

import logging

from app.runtime.pipeline import Step
from app.runtime.context import Context

logger = logging.getLogger("runtime.history_step")


class HistorySaveStep(Step):
    """Save the current conversation turn to file-based history storage.

    Runs after reply is generated. Delegates to RuntimeManager which
    handles JSON file persistence and index management.
    """

    async def run(self, ctx: Context) -> None:
        user_text = ctx.user_text or ctx.event.payload.get("text", "")
        reply_text = ctx.reply_text or ""

        if not user_text and not reply_text:
            return

        try:
            # Lazy import to avoid circular dependency:
            # runtime -> steps -> management -> runtime
            from app.runtime.management import get_manager
            mgr = get_manager()
            mgr.save_to_current_history(user_text, reply_text)
        except Exception:
            logger.exception("Failed to save conversation history")
