"""Tool Manager — stores formatted tool schemas and provides lookup."""

import logging
from typing import Any

from .types import FormattedTool

logger = logging.getLogger("bridge.mcp.tm")


class ToolManager:
    """Stores tool definitions and provides runtime lookup for execution."""

    def __init__(self, tools_openai: list[dict[str, Any]], tool_dict: dict[str, FormattedTool]) -> None:
        self._openai = tools_openai
        self._tool_dict = tool_dict
        logger.info("ToolManager: %d OpenAI tools, %d raw entries", len(tools_openai), len(tool_dict))

    @property
    def openai_tools(self) -> list[dict[str, Any]]:
        return self._openai

    def get_tool(self, name: str) -> FormattedTool | None:
        return self._tool_dict.get(name)
