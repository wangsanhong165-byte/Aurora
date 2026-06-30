"""MCP Client — manages persistent stdio connections to MCP servers."""

import logging
from contextlib import AsyncExitStack
from datetime import timedelta
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .server_registry import ServerRegistry

logger = logging.getLogger("bridge.mcp.client")
DEFAULT_TIMEOUT = timedelta(seconds=30)


class MCPClient:
    """Manages persistent connections to multiple MCP servers."""

    def __init__(self, server_registry: ServerRegistry) -> None:
        self._exit_stack = AsyncExitStack()
        self._sessions: dict[str, ClientSession] = {}
        self._tool_cache: dict[str, list[Any]] = {}
        self._registry = server_registry

    async def _ensure_session(self, server_name: str) -> ClientSession:
        """Get or create a session for the given server."""
        if server_name in self._sessions:
            return self._sessions[server_name]

        server = self._registry.get_server(server_name)
        if not server:
            raise ValueError(f"MCP server '{server_name}' not found")

        timeout = server.timeout or DEFAULT_TIMEOUT
        params = StdioServerParameters(
            command=server.command,
            args=server.args,
            env=server.env,
            cwd=server.cwd,
        )

        logger.info("Connecting to MCP server '%s'...", server_name)
        try:
            stdio = await self._exit_stack.enter_async_context(stdio_client(params))
            read, write = stdio
            session = await self._exit_stack.enter_async_context(
                ClientSession(read, write, read_timeout_seconds=timeout)
            )
            await session.initialize()
            self._sessions[server_name] = session
            logger.info("Connected to MCP server '%s'", server_name)
            return session
        except Exception as e:
            logger.error("Failed to connect MCP server '%s': %s", server_name, e)
            raise

    async def list_tools(self, server_name: str) -> list[Any]:
        """List tools available on a server (cached)."""
        if server_name in self._tool_cache:
            return self._tool_cache[server_name]

        session = await self._ensure_session(server_name)
        resp = await session.list_tools()
        self._tool_cache[server_name] = resp.tools
        return resp.tools

    async def call_tool(self, server_name: str, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Call a tool on the specified server. Returns formatted result dict."""
        session = await self._ensure_session(server_name)
        logger.info("Calling MCP tool '%s' on '%s'...", tool_name, server_name)

        response = await session.call_tool(tool_name, args)

        if response.isError:
            error_text = (
                response.content[0].text
                if response.content and hasattr(response.content[0], "text")
                else "Unknown server error"
            )
            logger.error("MCP tool '%s' error: %s", tool_name, error_text)
            return {"content_items": [{"type": "text", "text": f"Error: {error_text}"}]}

        items = []
        for item in response.content or []:
            entry: dict[str, Any] = {"type": getattr(item, "type", "text")}
            for attr in ("text", "data", "mimeType"):
                if hasattr(item, attr) and getattr(item, attr) is not None:
                    entry[attr] = getattr(item, attr)
            items.append(entry)

        if not items:
            items = [{"type": "text", "text": ""}]

        return {"content_items": items}

    async def __aenter__(self) -> "MCPClient":
        """Enter async context manager."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit async context manager — close all connections."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close all MCP connections."""
        n = len(self._sessions)
        await self._exit_stack.aclose()
        self._sessions.clear()
        self._tool_cache.clear()
        self._exit_stack = AsyncExitStack()
        logger.info("MCP: closed %d connection(s)", n)
