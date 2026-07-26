import asyncio

from app.interfaces.llm import LLMResponse, ToolCall
from app.runtime.character_turn import CharacterTurn, TurnInput
from app.runtime.steps.decision_step import DecisionStep


def test_many_tool_turns_remain_bounded_and_finish():
    class Tool:
        async def list_tools(self):
            return [{
                "type": "function",
                "function": {"name": "lookup", "parameters": {"type": "object"}},
                "risk": "read_only",
            }]

        async def execute(self, name, args):
            return "x" * 10000

    class LLM:
        def __init__(self):
            self.tool_turn = True

        async def generate(self, messages, **kwargs):
            if self.tool_turn and kwargs.get("tools"):
                self.tool_turn = False
                return LLMResponse(tool_calls=[ToolCall("lookup", {"q": "x"})])
            self.tool_turn = True
            return LLMResponse(
                reply="ok",
                segments=[{"text": "ok", "emotion": "neutral", "behavior": "speak"}],
            )

    async def exercise():
        step = DecisionStep(LLM(), tool_provider=Tool())
        for index in range(100):
            ctx = CharacterTurn(input=TurnInput(text=f"turn {index}"))
            await step.run(ctx)
            assert ctx.reply_text == "ok"
            assert ctx.context_budget["estimated_tokens"] <= 24000
            assert ctx.tool_result_budgets[0]["original_chars"] <= 6100
            assert ctx.tool_audit[0]["status"] == "ok"

    asyncio.run(exercise())
