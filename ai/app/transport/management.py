"""Management Handler — delegates to RuntimeManager.

Thin protocol layer: receives Command messages, calls RuntimeManager,
wraps results in CommandResponse/Error. Zero business logic.

This is the SOLE transport entry point for management operations.
The legacy bridge/server.py also delegates here for its inline handlers.
"""

from __future__ import annotations

import logging

from app.runtime.management import get_manager
from app.transport.protocol import Command, OutboundMessage, CommandResponse, Error

logger = logging.getLogger("transport.management")


class ManagementHandler:
    """Handles management/auxiliary operations for V2 WebSocket sessions.

    All operations delegate to runtime.RuntimeManager (the single source of truth).
    This handler only translates between protocol types and manager method calls.
    """

    def __init__(self):
        self._manager = get_manager()

    async def handle_command(self, message: Command) -> list[OutboundMessage]:
        """Route a Command message to RuntimeManager and return protocol response."""
        action = message.action
        params = message.params

        # ── History operations ──
        if action == "get_histories":
            return [CommandResponse(
                action="get_histories",
                data={"histories": self._manager.get_history_list()},
            )]

        elif action == "load_history":
            result = self._manager.load_history(params.get("history_uid", ""))
            return [CommandResponse(action="load_history", data=result)]

        elif action == "create_history":
            result = self._manager.create_history()
            return [CommandResponse(action="create_history", data=result)]

        elif action == "delete_history":
            result = self._manager.delete_history(params.get("history_uid", ""))
            return [CommandResponse(action="delete_history", data=result)]

        # ── Pinned memories ──
        elif action == "get_pinned":
            return [CommandResponse(
                action="get_pinned",
                data={"content": self._manager.get_pinned()},
            )]

        elif action == "set_pinned":
            content = self._manager.set_pinned(params.get("content", ""))
            return [CommandResponse(action="set_pinned", data={"content": content})]

        # ── Character management ──
        elif action == "switch_character":
            result = self._manager.switch_character(params.get("character_id", ""))
            if "error" in result:
                return [Error(code="switch_failed", message=result["error"])]
            return [CommandResponse(action="switch_character", data=result)]

        elif action == "reload_prompts":
            self._manager.reload_prompts()
            return [CommandResponse(action="reload_prompts", data={})]

        # ── Proactive system ──
        elif action == "set_proactive":
            self._manager.set_proactive(params.get("enabled", True))
            return [CommandResponse(
                action="set_proactive",
                data={"enabled": params.get("enabled", True)},
            )]

        elif action == "set_proactive_idle":
            seconds = int(params.get("seconds", 120))
            self._manager.set_proactive_idle(seconds)
            return [CommandResponse(
                action="set_proactive_idle",
                data={"seconds": seconds},
            )]

        else:
            return [Error(
                code="unknown_action",
                message=f"Unknown command action: {action}",
            )]
