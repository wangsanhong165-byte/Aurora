"""MCP (Model Context Protocol) module for LLM tool calling.

Adapted from Open-LLM-VTuber v1.2.1 mcpp/ package.
"""

from .types import MCPServer, FormattedTool, ToolCallObject, ToolCallFunctionObject
from .server_registry import ServerRegistry
from .mcp_client import MCPClient
from .tool_adapter import ToolAdapter
from .tool_manager import ToolManager
from .tool_executor import ToolExecutor

__all__ = [
    "MCPServer", "FormattedTool", "ToolCallObject", "ToolCallFunctionObject",
    "ServerRegistry", "MCPClient", "ToolAdapter", "ToolManager", "ToolExecutor",
]
