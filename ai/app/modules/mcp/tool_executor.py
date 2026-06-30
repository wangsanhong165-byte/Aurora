"""Tool Executor — runs MCP tool calls from the LLM and formats results."""

import json
import logging
from typing import Any

from .mcp_client import MCPClient
from .tool_manager import ToolManager

logger = logging.getLogger("bridge.mcp.exec")


class ToolExecutor:
    """Executes tool calls from the LLM via MCP and formats results."""

    def __init__(self, client: MCPClient, manager: ToolManager) -> None:
        self._client = client
        self._manager = manager

    async def call_tool(self, tool_name: str, args: dict[str, Any]) -> str:
        """Execute a tool by name. Returns a text string suitable for the LLM."""
        tool_info = self._manager.get_tool(tool_name)
        if not tool_info:
            logger.warning("Unknown tool '%s'", tool_name)
            return f"Error: Tool '{tool_name}' is not available."

        server_name = tool_info.related_server
        if not server_name:
            return f"Error: Tool '{tool_name}' has no associated server."

        logger.info("Executing '%s' on server '%s'", tool_name, server_name)
        try:
            result = await self._client.call_tool(server_name, tool_name, args)
        except Exception as e:
            logger.exception("Tool '%s' failed: %s", tool_name, e)
            return f"Error executing tool '{tool_name}': {e}"

        items = result.get("content_items", [])

        # Check for explicit error
        if items and items[0].get("type") == "error":
            return f"Error: {items[0].get('text', 'unknown')}"

        # Return text content
        texts: list[str] = []
        for item in items:
            if item.get("type") == "text":
                t = item.get("text", "")
                if t:
                    texts.append(t)
            elif item.get("type") == "image":
                texts.append("[Tool returned an image]")

        output = "\n".join(texts) if texts else ""
        logger.info("Tool '%s' returned %d chars", tool_name, len(output))
        return output
