"""Tool providers — registered on import."""
from pathlib import Path

from app.interfaces.tool import ToolInterface, MockTool
from app.providers.registry import provider_registry

provider_registry.register(ToolInterface, "mock", MockTool)

# Resolve config path relative to this file, not CWD
_MCP_CONFIG = Path(__file__).resolve().parents[3] / "config" / "mcp_servers.json"
if _MCP_CONFIG.exists():
    from app.providers.tool.legacy_provider import LegacyToolProvider

    provider_registry.register(ToolInterface, "legacy", LegacyToolProvider)
    provider_registry.register(ToolInterface, "default", LegacyToolProvider)
else:
    provider_registry.register(ToolInterface, "default", MockTool)
