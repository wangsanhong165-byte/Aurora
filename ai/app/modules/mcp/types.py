"""MCP data types — dataclasses for MCP servers and tool definitions."""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional, Any


@dataclass
class MCPServer:
    """An MCP server definition.

    Args:
        name: Server identifier.
        command: Executable command (npx, uvx, node, etc.).
        args: CLI arguments for the command.
        env: Optional environment variables.
        cwd: Optional working directory.
        timeout: Connection timeout (default 30s).
    """
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: Optional[dict[str, str]] = None
    cwd: str | None = None
    timeout: Optional[timedelta] = timedelta(seconds=30)
    description: str = "No description available."


@dataclass
class FormattedTool:
    """A tool formatted for LLM API consumption.

    Args:
        input_schema: JSON schema for tool parameters.
        related_server: Name of the MCP server providing this tool.
        description: Human-readable tool description.
    """
    input_schema: dict[str, Any]
    related_server: str
    description: str = "No description available."


@dataclass
class ToolCallFunctionObject:
    """Function object inside a tool call (mimics OpenAI API structure)."""
    name: str = ""
    arguments: str = ""


@dataclass
class ToolCallObject:
    """A tool call from the LLM (mimics OpenAI ChatCompletionMessageToolCall)."""
    id: Optional[str] = None
    type: str = "function"
    index: int = 0
    function: ToolCallFunctionObject = field(default_factory=ToolCallFunctionObject)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolCallObject":
        return cls(
            id=data["id"],
            type=data["type"],
            index=data["index"],
            function=ToolCallFunctionObject(
                name=data["function"]["name"],
                arguments=data["function"]["arguments"],
            ),
        )
