"""Management Handler — delegates to RuntimeManager.

Thin protocol layer: receives Command messages, calls RuntimeManager,
wraps results in CommandResponse/Error. Zero business logic.

This is the sole WebSocket transport entry point for management operations.
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

        elif action == "get_memories":
            return [CommandResponse(
                action="get_memories",
                data={"memories": self._manager.get_memories(
                    bool(params.get("include_inactive", False)),
                    int(params.get("limit", 200)),
                )},
            )]

        elif action == "get_character_self_view":
            return [CommandResponse(
                action=action,
                data={"view": self._manager.get_character_self_view()},
            )]

        elif action == "get_memory_view":
            return [CommandResponse(
                action=action,
                data={"view": self._manager.get_memory_view(
                    query=str(params.get("query", "")),
                    category=str(params.get("category", "all")),
                    limit=int(params.get("limit", 200)),
                )},
            )]

        elif action == "update_memory_view":
            result = self._manager.update_memory_view(
                str(params.get("ref", "")), params
            )
            if "error" in result:
                return [Error(code="memory_update_failed", message=result["error"])]
            return [CommandResponse(action=action, data=result)]

        elif action == "forget_memory_view":
            result = self._manager.forget_memory_view(str(params.get("ref", "")))
            if "error" in result:
                return [Error(code="memory_forget_failed", message=result["error"])]
            return [CommandResponse(action=action, data=result)]

        elif action == "get_voice_status_view":
            return [CommandResponse(
                action=action,
                data={"view": self._manager.get_voice_status_view()},
            )]

        elif action == "get_capability_view":
            return [CommandResponse(
                action=action,
                data={"view": await self._manager.get_capability_view()},
            )]

        elif action == "get_turns":
            return [CommandResponse(
                action=action,
                data={"turns": self._manager.get_turns(
                    int(params.get("limit", 100))
                )},
            )]

        elif action == "get_turn_detail":
            result = self._manager.get_turn_detail(str(params.get("turn_id", "")))
            if "error" in result:
                return [Error(code="turn_not_found", message=result["error"])]
            return [CommandResponse(action=action, data=result)]

        elif action == "get_runtime_diagnostics":
            return [CommandResponse(
                action=action,
                data=self._manager.get_runtime_diagnostics(),
            )]

        elif action == "update_memory":
            result = self._manager.update_memory(int(params.get("memory_id", 0)), params)
            if "error" in result:
                return [Error(code="memory_update_failed", message=result["error"])]
            return [CommandResponse(action="update_memory", data=result)]

        elif action == "forget_memory":
            result = self._manager.forget_memory(int(params.get("memory_id", 0)))
            return [CommandResponse(action="forget_memory", data=result)]

        elif action == "get_system_metrics":
            return [CommandResponse(
                action="get_system_metrics",
                data=self._manager.get_system_metrics(),
            )]

        elif action == "get_tools":
            return [CommandResponse(
                action="get_tools",
                data={"tools": await self._manager.get_tools()},
            )]

        elif action == "set_tool_enabled":
            result = self._manager.set_tool_enabled(
                str(params.get("name", "")), bool(params.get("enabled", True))
            )
            if "error" in result:
                return [Error(code="tool_settings_failed", message=result["error"])]
            return [CommandResponse(action="set_tool_enabled", data=result)]

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
