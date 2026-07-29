from __future__ import annotations

import asyncio

from app.providers.tool.legacy_provider import LegacyToolProvider


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
