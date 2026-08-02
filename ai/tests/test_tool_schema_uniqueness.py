from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.providers.tool.legacy_provider import LegacyToolProvider
from app.modules.mcp import tool_adapter as tool_adapter_module


def _schema(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": name,
            "parameters": {"type": "object", "properties": {}},
        },
    }


def test_builtin_tool_wins_when_mcp_exposes_the_same_name() -> None:
    provider = LegacyToolProvider(mcp_config_path="missing-mcp-config.json")
    provider._mcp_initialized = True
    provider._mcp_tool_names = {"get_current_time", "web_search"}
    provider._openai_schemas = [
        _schema("get_current_time"),
        _schema("web_search"),
    ]

    schemas = asyncio.run(provider.list_tools())
    names = [schema["function"]["name"] for schema in schemas]

    assert names.count("get_current_time") == 1
    assert names.count("web_search") == 1
    assert "get_current_time" not in provider._mcp_tool_names


def test_mcp_schema_list_is_deduplicated_before_llm_request() -> None:
    provider = LegacyToolProvider(mcp_config_path="missing-mcp-config.json")
    provider._mcp_initialized = True
    provider._mcp_tool_names = {"web_search"}
    provider._openai_schemas = [
        _schema("web_search"),
        _schema("web_search"),
    ]

    schemas = asyncio.run(provider.list_tools())
    names = [schema["function"]["name"] for schema in schemas]

    assert names.count("web_search") == 1


def test_mcp_adapter_keeps_partial_results_and_records_failed_servers(monkeypatch):
    class FakeClient:
        def __init__(self, registry):
            self.registry = registry

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def list_tools(self, server_name):
            if server_name == "broken":
                raise RuntimeError("server unavailable")
            return [SimpleNamespace(
                name="web_search",
                description="Search the web",
                inputSchema={"properties": {}, "required": []},
            )]

    monkeypatch.setattr(tool_adapter_module, "MCPClient", FakeClient)
    registry = SimpleNamespace(servers={"broken": object(), "healthy": object()})
    adapter = tool_adapter_module.ToolAdapter(registry)

    schemas, tools = asyncio.run(adapter.get_tools(["broken", "healthy"]))

    assert [schema["function"]["name"] for schema in schemas] == ["web_search"]
    assert list(tools) == ["web_search"]
    assert adapter.failed_servers == {"broken"}
