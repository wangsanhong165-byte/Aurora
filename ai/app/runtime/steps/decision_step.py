"""DecisionStep — thin orchestrator for planner → LLM → tools → response.

Composes: DefaultPlanner → PromptCompiler → LLM.generate → ToolCoordinator → ResponseInterpreter

Extracted to separate services:
  - DefaultPlanner -> app/runtime/default_planner.py
  - ToolCoordinator -> app/runtime/tool_coordinator.py
  - PromptCompiler -> app/runtime/prompt_compiler.py (already separate)
  - ResponseInterpreter -> app/runtime/response_interpreter.py (already separate)
  - ResponseValidator -> app/runtime/response_validator.py (already separate)
  - ToolExecutionSupervisor -> app/runtime/tool_execution.py (already separate)
  - ToolPolicy -> app/runtime/tool_policy.py (already separate)
  - ContextBudget -> app/runtime/context_budget.py (already separate)
"""

import logging
import os
import json as _json
from typing import Any

logger = logging.getLogger("decision_step")

from app.runtime.pipeline import Step
from app.runtime.character_turn import CharacterTurn
from app.interfaces.llm import LLMInterface, LLMResponse
from app.interfaces.tool import ToolInterface
from app.runtime.default_planner import DefaultPlanner, Plan
from app.runtime.tool_coordinator import ToolCoordinator

_MAX_TOOL_ROUNDS = min(3, max(1, int(os.environ.get("AGENT_MAX_TOOL_ROUNDS", "3"))))


class DecisionStep(Step):
    """Strategy combination: Planner → PromptCompiler → Reasoner.

    Calls the LLM, delegates tool-calling to ToolCoordinator, then produces
    final reply. Adds turns to conversation history.

    Protocol-agnostic: consumes LLMResponse canonical objects.
    No provider detection, no json.loads, no nested parsing.
    """

    def __init__(
        self,
        llm: LLMInterface,
        tool_provider: ToolInterface | None = None,
        planner=None,
        tool_supervisor=None,
    ):
        self.llm = llm
        self.tools = tool_provider
        self.planner = planner or DefaultPlanner()
        from app.runtime.prompt_compiler import PromptCompiler
        from app.runtime.response_interpreter import ResponseInterpreter
        self.prompt_compiler = PromptCompiler(self.planner)
        self.response_interpreter = ResponseInterpreter()
        self.tool_coordinator = ToolCoordinator(
            tools=tool_provider,
            tool_supervisor=tool_supervisor,
            max_rounds=_MAX_TOOL_ROUNDS,
        )

    async def run(self, ctx: CharacterTurn) -> None:
        from app.runtime.response_validator import ResponseValidator
        from app.runtime.tool_policy import ToolPolicy

        compiled = self.prompt_compiler.compile(ctx, ctx.character_self)
        messages = list(compiled.messages)
        from app.runtime.context_budget import ContextBudget
        context_budget = ContextBudget()
        messages, budget_report = context_budget.fit_messages(messages)
        ctx.context_budget = budget_report

        user_text = ctx.user_text or ctx.event.payload.get("text", "")

        # Resolve tool schemas once, before the loop
        tool_schemas: list[dict] | None = None
        if self.tools is not None:
            try:
                tool_schemas = await self.tools.list_tools()
                tool_schemas = ToolPolicy().filter_schemas(
                    tool_schemas, input_origin=ctx.input_origin
                )
            except Exception:
                logger.warning("Failed to list tools — tool calling disabled")

        # Delegate tool loop to ToolCoordinator
        def _llm_gen(msgs, tools=None):
            return self.llm.generate(msgs, tools=tools)

        messages, response, accumulated_usage, final_reply = await self.tool_coordinator.execute_loop(
            messages, ctx, tool_schemas, context_budget, _llm_gen
        )

        from app.modules.tts_preprocessor import split_reasoning

        safe = ResponseValidator().validate(
            final_reply or response.reply, response.segments or []
        )
        if not safe.valid:
            messages.append({
                "role": "assistant",
                "content": final_reply or response.reply,
            })
            messages.append({
                "role": "system",
                "content": (
                    "Your previous response was invalid structured output. "
                    "Repair it now. Return only the required valid JSON object; "
                    "preserve the intended meaning and do not call tools."
                ),
            })
            repair = await self.llm.generate(messages, tools=None, temperature=0)
            accumulated_usage.add(repair.usage)
            response = repair
            safe = ResponseValidator().validate(
                repair.reply, repair.segments or []
            )
        clean_reply, tagged_reasoning = split_reasoning(safe.reply)
        interpreted = self.response_interpreter.interpret(
            LLMResponse(
                reply=clean_reply,
                reasoning=response.reasoning,
                segments=safe.segments,
                tool_calls=response.tool_calls,
                usage=response.usage,
            ),
            ctx,
        )
        ctx.reply_text = interpreted.reply_text
        ctx.segments = interpreted.segments
        ctx.output.performance = interpreted.performance
        ctx.warnings.extend(interpreted.warnings)
        from app.runtime.usage import usage_report
        ctx.llm_usage = usage_report(accumulated_usage)
        provider_reasoning = (response.reasoning or "").strip()
        ctx.reasoning = "\n\n".join(part for part in (provider_reasoning, tagged_reasoning) if part)

        # Extract segments from the final LLM response
        segments = interpreted.segments
        if segments:
            ctx.segments = segments
            last_emotion = segments[-1].get("emotion", "")
            if last_emotion:
                ctx.emotion = last_emotion

        # Add turns to conversation
        conversation = ctx.conversation
        if conversation is not None:
            if user_text and ctx.input_origin == "user":
                conversation.add_turn("user", user_text)
            if ctx.reply_text:
                conversation.add_turn("assistant", ctx.reply_text)
