import json
from pathlib import Path

from app.modules.mcp import server_registry as server_registry_module
from app.modules.mcp.server_registry import ServerRegistry


def test_uvx_server_uses_workspace_writable_runtime_directories(tmp_path: Path):
    config_path = tmp_path / "config" / "mcp_servers.json"
    config_path.parent.mkdir()
    config_path.write_text(
        json.dumps(
            {
                "mcp_servers": {
                    "search": {
                        "command": "uvx",
                        "args": ["example-mcp"],
                        "env": {"EXAMPLE_FLAG": "1"},
                    },
                    "python-server": {
                        "command": "python",
                        "args": ["-m", "example_mcp"],
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    registry = ServerRegistry(config_path)

    search = registry.get_server("search")
    assert search is not None
    assert Path(search.env["UV_CACHE_DIR"]) == tmp_path / ".uv_cache"
    assert Path(search.env["UV_TOOL_DIR"]) == tmp_path / ".uv_tools"
    assert Path(search.env["UV_PYTHON_INSTALL_DIR"]) == tmp_path / ".uv_tools" / "python"
    assert search.env["EXAMPLE_FLAG"] == "1"

    python_server = registry.get_server("python-server")
    assert python_server is not None
    assert Path(python_server.command).name.lower() == "python.exe"
    assert python_server.env is None


def test_uvx_server_reuses_available_python_runtime(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "config" / "mcp_servers.json"
    config_path.parent.mkdir()
    config_path.write_text(
        json.dumps(
            {"mcp_servers": {"search": {"command": "uvx", "args": ["example-mcp"]}}}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        server_registry_module.shutil,
        "which",
        lambda name: "D:/conda/python.exe" if name == "python" else f"{name}.exe",
    )

    search = ServerRegistry(config_path).get_server("search")

    assert search is not None
    assert search.env["UV_PYTHON"] == "D:/conda/python.exe"
