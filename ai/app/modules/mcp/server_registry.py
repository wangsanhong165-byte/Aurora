"""MCP Server Registry — loads server definitions from mcp_servers.json."""

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Optional

from .types import MCPServer

logger = logging.getLogger("bridge.mcp.sr")


class ServerRegistry:
    """Manages MCP server definitions loaded from a JSON config file."""

    def __init__(self, config_path: str | Path) -> None:
        self.servers: dict[str, MCPServer] = {}

        config_path = Path(config_path).absolute()
        if not config_path.exists() or not config_path.is_file():
            logger.warning("MCP config '%s' not found — MCP disabled.", config_path)
            return

        raw: dict[str, Any] = json.loads(config_path.read_text("utf-8"))
        servers_cfg: dict[str, Any] = raw.get("mcp_servers", {})

        if not servers_cfg:
            logger.warning("No MCP servers defined in config.")
            return

        npx_ok = shutil.which("npx") is not None
        uvx_ok = shutil.which("uvx") is not None
        node_ok = shutil.which("node") is not None

        for name, details in servers_cfg.items():
            if "command" not in details:
                logger.warning("Server '%s': missing 'command', skipping.", name)
                continue

            cmd = details["command"]
            if cmd == "npx" and not npx_ok:
                logger.warning("npx not found — skipping server '%s'", name)
                continue
            if cmd == "uvx" and not uvx_ok:
                logger.warning("uvx not found — skipping server '%s'", name)
                continue
            if cmd == "node" and not node_ok:
                logger.warning("node not found — skipping server '%s'", name)
                continue

            self.servers[name] = MCPServer(
                name=name,
                command=cmd,
                args=details.get("args", []),
                env=details.get("env"),
                cwd=details.get("cwd"),
            )
            logger.info("Loaded MCP server: '%s' (%s %s)", name, cmd, " ".join(details.get("args", [])))

    def get_server(self, name: str) -> Optional[MCPServer]:
        return self.servers.get(name)
