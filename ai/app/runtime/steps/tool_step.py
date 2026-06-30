from app.runtime.pipeline import Step
from app.runtime.context import Context
from app.interfaces.tool import ToolInterface


class ToolStep(Step):
    """Execute tool calls found in the LLM response."""

    def __init__(self, tool_provider: ToolInterface):
        self.tools = tool_provider

    async def run(self, ctx: Context) -> None:
        tool_calls = ctx.state.get("tool_calls", [])
        for call in tool_calls:
            name = call.get("name", "")
            args = call.get("args", {})
            result = await self.tools.execute(name, args)
            ctx.state.setdefault("tool_results", []).append({
                "name": name,
                "result": result,
            })
