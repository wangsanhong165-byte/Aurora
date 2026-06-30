"""LegacyToolProvider — implements ToolInterface via legacy ToolRegistry + MCP.

Wraps the production tool execution system:
  - Builtin tools (screen_capture) via ToolRegistry → asyncio.to_thread
  - MCP tools via ToolExecutor → async MCP calls (lazy-init on first use)

Architecture:
  LegacyToolProvider.execute(name, args)
    ├── name in MCP → ToolExecutor.call_tool(name, args)     ──→ MCP server
    └── name not in MCP → asyncio.to_thread(reg.execute, n, a)  → sync tool fn
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.interfaces.tool import ToolInterface
from app.legacy.tools.registry import ToolRegistry
from app.legacy.tools.builtins.screen import _register_all as _register_builtins

logger = logging.getLogger("legacy.tool_provider")


class LegacyToolProvider(ToolInterface):
    """ToolInterface backed by legacy ToolRegistry (builtins) + MCP tools.

    Builtin tools are registered at construction time. MCP tools are
    lazily discovered on the first call to execute() or list_tools(),
    after which a persistent MCPClient connection pool is kept until
    shutdown().

    Production path:
      execute("screen_capture", {"region": "full"})
        → ToolRegistry.execute("screen_capture", {"region": "full"})
        → screen_capture(region="full") → JSON string

      execute("get_time", {"timezone": "Asia/Shanghai"})
        → ToolExecutor.call_tool("get_time", {"timezone": "Asia/Shanghai"})
        → MCPClient.call_tool("time", "get_time", ...) → text result
    """

    def __init__(self, mcp_config_path: str | None = None) -> None:
        self._registry = ToolRegistry()
        _register_builtins(self._registry)

        self._mcp_executor: object | None = None
        self._mcp_tool_names: set[str] = set()
        self._openai_schemas: list[dict] = []
        self._mcp_initialized = False
        self._mcp_config_path = mcp_config_path or str(
            Path("config/mcp_servers.json").absolute()
        )

    # ── lazy MCP initialisation ──────────────────────────────────────────

    async def _ensure_mcp(self) -> None:
        """Discover MCP tools and create persistent executor (once)."""
        if self._mcp_initialized:
            return
        self._mcp_initialized = True

        config_path = Path(self._mcp_config_path)
        if not config_path.exists():
            logger.info("MCP config '%s' not found — MCP disabled", config_path)
            return

        try:
            from app.modules.mcp import (
                MCPClient,
                ServerRegistry,
                ToolAdapter,
                ToolExecutor,
                ToolManager,
            )

            registry = ServerRegistry(str(config_path))
            enabled_servers = list(registry.servers.keys())
            if not enabled_servers:
                logger.info("No enabled MCP servers — MCP disabled")
                return

            # One-shot discovery (temporary connections)
            adapter = ToolAdapter(registry)
            openai_tools, tool_dict = await adapter.get_tools(enabled_servers)

            # Persistent client + executor for runtime execution
            client = MCPClient(registry)
            manager = ToolManager(openai_tools, tool_dict)
            self._mcp_executor = ToolExecutor(client, manager)
            self._mcp_tool_names = set(tool_dict.keys())
            self._openai_schemas = openai_tools

            logger.info(
                "MCP initialised: %d tool(s) from %d server(s)",
                len(tool_dict),
                len(enabled_servers),
            )
        except Exception:
            logger.exception("MCP initialisation failed — MCP tools disabled")
            self._mcp_initialized = False

    # ── ToolInterface ────────────────────────────────────────────────────

    async def execute(self, name: str, args: dict) -> str:
        """Execute a tool by name.

        MCP tools are dispatched via ToolExecutor (async).
        Builtin/plugin tools fall through to ToolRegistry (sync → thread pool).
        """
        await self._ensure_mcp()

        if name in self._mcp_tool_names and self._mcp_executor is not None:
            # Import locally to avoid circular dependency at module level
            from app.modules.mcp import ToolExecutor as _TExec

            executor = self._mcp_executor
            assert isinstance(executor, _TExec)
            try:
                return await executor.call_tool(name, args)
            except Exception as exc:
                logger.exception("MCP tool '%s' failed", name)
                return f"Error: {exc}"

        return await asyncio.to_thread(self._registry.execute, name, args)

    async def list_tools(self) -> list[dict]:
        """Return all available tools (builtins + MCP) as a dict list."""
        await self._ensure_mcp()

        builtin_schemas = self._registry.list_openai_schemas()
        return builtin_schemas + self._openai_schemas

    # ── lifecycle ────────────────────────────────────────────────────────

    async def shutdown(self) -> None:
        """Close persistent MCP connections."""
        if self._mcp_executor is not None:
            client = getattr(self._mcp_executor, "_client", None)
            if client is not None and hasattr(client, "aclose"):
                await client.aclose()
                logger.info("MCP connections closed")
