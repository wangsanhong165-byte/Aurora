"""Tool Adapter — discovers tools from MCP servers and formats them for LLM APIs."""

import logging
from typing import Any

from .types import FormattedTool
from .mcp_client import MCPClient
from .server_registry import ServerRegistry

logger = logging.getLogger("bridge.mcp.adapter")


class ToolAdapter:
    """Discovers MCP tools and formats them for OpenAI-compatible function calling."""

    def __init__(self, server_registry: ServerRegistry) -> None:
        self._registry = server_registry
        self.failed_servers: set[str] = set()

    async def get_tools(self, enabled_servers: list[str]) -> tuple[list[dict[str, Any]], dict[str, FormattedTool]]:
        """Fetch tool schemas from enabled servers.

        Returns:
            (openai_tools_list, tool_dict) where openai_tools_list is formatted
            for the OpenAI tools= parameter, and tool_dict maps tool names to
            FormattedTool metadata (for execution routing).
        """
        openai_tools: list[dict[str, Any]] = []
        tool_dict: dict[str, FormattedTool] = {}
        self.failed_servers.clear()

        if not enabled_servers:
            return openai_tools, tool_dict

        async with MCPClient(self._registry) as client:
            for server_name in enabled_servers:
                if server_name not in self._registry.servers:
                    logger.warning("Server '%s' not in registry, skipping", server_name)
                    continue

                try:
                    result = await client.list_tools(server_name)
                    tools = result.tools if hasattr(result, 'tools') else list(result)
                except Exception as e:
                    self.failed_servers.add(server_name)
                    logger.error("Failed to list tools on '%s': %s", server_name, e)
                    continue

                logger.info("Discovered %d tool(s) on '%s'", len(tools), server_name)

                for tool in tools:
                    schema = tool.inputSchema
                    description = tool.description or "No description."

                    # Store for execution routing
                    tool_dict[tool.name] = FormattedTool(
                        input_schema=schema,
                        related_server=server_name,
                        description=description,
                    )

                    # Format as OpenAI tool schema
                    params: dict[str, Any] = {
                        "type": "object",
                        "properties": {},
                        "required": schema.get("required", []),
                    }
                    props = schema.get("properties", {})
                    for pname, pinfo in props.items():
                        entry: dict[str, Any] = {
                            "type": pinfo.get("type", "string"),
                            "description": pinfo.get("description", ""),
                        }
                        if "enum" in pinfo:
                            entry["enum"] = pinfo["enum"]
                        if entry["type"] == "array" and "items" in pinfo:
                            entry["items"] = pinfo["items"]
                        params["properties"][pname] = entry

                    openai_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": description,
                            "parameters": params,
                        },
                    })

        return openai_tools, tool_dict
