"""Legacy shim — re-exports from app.legacy.tools."""
from app.legacy.tools.registry import ToolRegistry, Tool
from app.legacy.tools.builtins.screen import _register_all

__all__ = ["ToolRegistry", "Tool", "_register_all"]
