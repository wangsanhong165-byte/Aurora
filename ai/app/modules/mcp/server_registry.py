"""MCP Server Registry — loads server definitions from mcp_servers.json."""

import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Optional

from .types import MCPServer

logger = logging.getLogger("bridge.mcp.sr")


def _is_windows_store_alias(value: str | None) -> bool:
    return "windowsapps" in str(value or "").casefold()


def _resolve_python_executable() -> str | None:
    """Resolve a real Python for MCP child processes.

    Windows may expose the Microsoft Store ``python.exe`` alias through PATH
    even when the application itself is running inside a working Conda
    environment.  That alias exits with 9009 when used as an MCP child
    interpreter, so prefer an explicit override, a real PATH entry, or the
    Conda base interpreter beside the active environment.
    """
    candidates: list[tuple[str | None, bool]] = [
        (os.environ.get("SOULLINK_MCP_PYTHON"), True),
        (os.environ.get("MCP_PYTHON"), True),
        (shutil.which("python"), False),
    ]

    executable = Path(sys.executable)
    if len(executable.parents) >= 3 and executable.parent.parent.name.casefold() == "envs":
        candidates.append((str(executable.parents[2] / "python.exe"), True))
    if sys.base_prefix and sys.base_prefix != sys.prefix:
        candidates.append((str(Path(sys.base_prefix) / "python.exe"), True))
    candidates.append((str(executable), True))

    for candidate, require_exists in candidates:
        if not candidate or _is_windows_store_alias(candidate):
            continue
        if require_exists and not Path(candidate).exists():
            continue
        return str(candidate)
    return None


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
        python_executable = _resolve_python_executable()

        for name, details in servers_cfg.items():
            if "command" not in details:
                logger.warning("Server '%s': missing 'command', skipping.", name)
                continue

            cmd = details["command"]
            if cmd == "python" and python_executable:
                cmd = python_executable
            if cmd == "npx" and not npx_ok:
                logger.warning("npx not found — skipping server '%s'", name)
                continue
            if cmd == "uvx" and not uvx_ok:
                logger.warning("uvx not found — skipping server '%s'", name)
                continue
            if cmd == "node" and not node_ok:
                logger.warning("node not found — skipping server '%s'", name)
                continue

            env = details.get("env")
            if cmd == "uvx":
                workspace_root = config_path.parent.parent
                env = {
                    **os.environ,
                    "UV_CACHE_DIR": str(workspace_root / ".uv_cache"),
                    "UV_TOOL_DIR": str(workspace_root / ".uv_tools"),
                    "UV_PYTHON_INSTALL_DIR": str(
                        workspace_root / ".uv_tools" / "python"
                    ),
                    **{
                        str(key): str(value)
                        for key, value in (details.get("env") or {}).items()
                    },
                }
                if python_executable:
                    # Keep uvx on the already provisioned Python runtime.  If
                    # this is omitted, uv may try to download a managed
                    # interpreter during MCP discovery and drop the server.
                    env.setdefault("UV_PYTHON", python_executable)

            self.servers[name] = MCPServer(
                name=name,
                command=cmd,
                args=details.get("args", []),
                env=env,
                cwd=details.get("cwd"),
            )
            logger.info("Loaded MCP server: '%s' (%s %s)", name, cmd, " ".join(details.get("args", [])))

    def get_server(self, name: str) -> Optional[MCPServer]:
        return self.servers.get(name)
