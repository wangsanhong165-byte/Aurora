"""ToolRegistry ? unified tool registration, permission control, and execution."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

RiskLevel = str  # "safe" | "confirm" | "dangerous"
ConfirmPolicy = str  # "auto_allow" | "ask_user" | "deny"


@dataclass
class Tool:
    name: str
    fn: Callable[..., Any]
    description: str
    group: str = "builtin"             # builtin / plugin / mcp
    risk: RiskLevel = "safe"
    confirm: ConfirmPolicy = "auto_allow"
    enabled: bool = True
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": list(self.parameters.keys()),
                },
            },
        }


class ToolRegistry:
    """Unified tool registry with group-based capability toggles."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._groups_enabled: dict[str, bool] = {
            "builtin": True,
            "plugin": True,
            "mcp": True,
        }

    # ---- registration ----------------------------------------------------
    def register(
        self,
        name: str,
        fn: Callable,
        description: str = "",
        group: str = "builtin",
        risk: RiskLevel = "safe",
        confirm: ConfirmPolicy = "auto_allow",
        parameters: dict[str, Any] | None = None,
    ) -> None:
        self._tools[name] = Tool(
            name=name,
            fn=fn,
            description=description,
            group=group,
            risk=risk,
            confirm=confirm,
            parameters=parameters or {},
        )

    def remove(self, name: str) -> None:
        self._tools.pop(name, None)

    # ---- group control ---------------------------------------------------
    def set_group(self, group: str, enabled: bool) -> None:
        self._groups_enabled[group] = enabled

    def is_group_enabled(self, group: str) -> bool:
        return self._groups_enabled.get(group, False)

    # ---- query -----------------------------------------------------------
    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_all(self) -> list[Tool]:
        return list(self._tools.values())

    def list_openai_schemas(self) -> list[dict[str, Any]]:
        """Return tool schemas in OpenAI tool_calls format, respecting group toggles."""
        schemas = []
        for tool in self._tools.values():
            if not tool.enabled:
                continue
            if not self._groups_enabled.get(tool.group, False):
                continue
            schemas.append(tool.to_openai_schema())
        return schemas

    # ---- execution -------------------------------------------------------
    def execute(self, name: str, args: dict[str, Any]) -> str:
        """Execute a tool and return result as JSON string.
        
        Returns error JSON if tool not found, group disabled, or execution fails.
        """
        tool = self._tools.get(name)
        if tool is None:
            return json.dumps({"error": f"tool not found: {name}"})
        if not tool.enabled:
            return json.dumps({"error": f"tool disabled: {name}"})
        if not self._groups_enabled.get(tool.group, False):
            return json.dumps({"error": f"group disabled: {tool.group}"})
        try:
            result = tool.fn(**args)
            if isinstance(result, str):
                return result
            return json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def needs_confirm(self, name: str) -> ConfirmPolicy:
        tool = self._tools.get(name)
        if tool is None:
            return "deny"
        return tool.confirm

    def __repr__(self) -> str:
        return f"ToolRegistry(tools={list(self._tools)!r})"
