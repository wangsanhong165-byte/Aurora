
import sys
sys.path.insert(0, '.')
import asyncio, threading

from app.tools.registry import ToolRegistry
from app.mcp.tool_adapter import ToolAdapter
from app.mcp.server_registry import ServerRegistry
from app.mcp.tool_executor import ToolExecutor
from app.mcp.mcp_client import MCPClient
from app.mcp.tool_manager import ToolManager

_mcp_loop = None
_loop_ready = threading.Event()

def _ensure_loop():
    global _mcp_loop
    if _mcp_loop is None or not _mcp_loop.is_running():
        _mcp_loop = asyncio.new_event_loop()
        t = threading.Thread(target=_mcp_loop.run_forever, daemon=True, name='mcp-loop')
        t.start()
        _loop_ready.set()
    return _mcp_loop

def _call_mcp_sync(executor, tool_name, tool_input):
    loop = _ensure_loop()
    future = asyncio.run_coroutine_threadsafe(
        executor.run_single_tool(tool_name, tool_name, tool_input or {}), loop)
    is_error, text_content, metadata, content_items = future.result(timeout=60)
    if is_error:
        return 'Error: ' + text_content
    for item in content_items:
        if item.get('type') == 'text':
            return item.get('text', '')
    return text_content

async def register_mcp_tools(registry, enabled_servers=None):
    if enabled_servers is None:
        enabled_servers = ['time', 'ddg-search']
    sr = ServerRegistry('mcp_servers.json')
    adapter = ToolAdapter(sr)
    servers_info, formatted_tools = await adapter.get_server_and_tool_info(enabled_servers)
    openai_tools, _ = adapter.format_tools_for_api(formatted_tools)
    tm = ToolManager(formatted_tools_openai=openai_tools, formatted_tools_claude=[], initial_tools_dict=formatted_tools)
    client = MCPClient(sr)
    executor = ToolExecutor(client, tm)
    for schema in openai_tools:
        name = schema['function']['name']
        fn = (lambda n: lambda **kw: _call_mcp_sync(executor, n, kw))(name)
        registry.register(name=name, fn=fn, description=schema['function'].get('description', ''), group='mcp', parameters=schema['function'].get('parameters', {}).get('properties', {}))
    print(f'[MCP] Registered {len(openai_tools)} tools from: {enabled_servers}')
    return openai_tools
