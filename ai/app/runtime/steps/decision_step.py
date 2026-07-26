"""DecisionStep — replaces the old Brain.

Composes: Planner → PromptCompiler → LLM.generate → ResponseParser

DecisionStep is protocol-agnostic. It consumes LLMResponse canonical
objects — no json.loads, no provider detection, no nested parsing.
All provider-specific normalization happens inside the provider layer.
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
from app.runtime.character_intent import EMOTIONS, BEHAVIORS

_MAX_TOOL_ROUNDS = min(3, max(1, int(os.environ.get("AGENT_MAX_TOOL_ROUNDS", "3"))))

class DefaultPlanner:
    """Build message list from character, memories, conversation, and user input."""

    def plan(self, ctx: CharacterTurn) -> "Plan":
        messages: list[dict[str, str]] = []

        character = ctx.character

        # 0. Language lock — placed FIRST so it overrides everything else
        prompt_lang = "en"
        if character is not None:
            card = character.raw_card if hasattr(character, "raw_card") else {}
            if isinstance(card, dict):
                prompt_lang = card.get("tts", {}).get("prompt_lang", "en")
        native_map = {"en": "English", "ja": "Japanese", "zh": "Chinese", "ko": "Korean"}
        nl = native_map.get(prompt_lang, "English")
        messages.append({
            "role": "system",
            "content": f"LANGUAGE LOCK: You must output {nl} only. Never use Chinese — even if the user writes in Chinese.",
        })

        # 1. System prompt from character
        if character is not None:
            persona = getattr(character, "persona", None)
            if persona is not None:
                system_text = persona.setting or ""
                if persona.name:
                    system_text = f"You are {persona.name}.\n{system_text}"
                if system_text:
                    messages.append({"role": "system", "content": system_text})

        if not messages:
            messages.append({
                "role": "system",
                "content": "You are a helpful assistant. Respond concisely.",
            })

        # 2. Retrieved memories as context (from SQLiteMemory)
        memories = ctx.memories
        if memories:
            from app.runtime.context_assembler import ContextAssembler
            compiled_memory, memory_parts = ContextAssembler().assemble_memories(memories)

            if compiled_memory:
                messages.append({
                    "role": "system",
                    "content": "Compiled memory context:\n" + compiled_memory,
                })

            if memory_parts:
                messages.append({
                    "role": "system",
                    "content": "Relevant past context:\n" + "\n---\n".join(memory_parts),
                })

        # 3. Conversation history
        conversation = ctx.conversation
        if conversation is not None:
            history = conversation.get_history(limit=10)
            messages.extend(history)

        # 3b. Current emotion context (before format instructions, so LLM sees it naturally)
        if character is not None:
            current_emotion = getattr(character.emotion, "current", "")
            if current_emotion and current_emotion != "neutral":
                messages.append({
                    "role": "system",
                    "content": (
                        f"Current emotion: {current_emotion}. "
                        "Let this naturally influence your tone and phrasing."
                    ),
                })
            from app.runtime.context_assembler import ContextAssembler
            messages.append({
                "role": "system",
                "content": ContextAssembler().assemble_character_state(character),
            })

        # 4. Output format instructions
        if character is not None:
            card = character.raw_card if hasattr(character, 'raw_card') else {}
            if isinstance(card, dict):
                tts_cfg = card.get('tts', {})
                prompt_lang = tts_cfg.get('prompt_lang', 'ja')
            else:
                prompt_lang = 'ja'
        else:
            prompt_lang = 'ja'

        native_map = {'en': 'English', 'ja': 'Japanese', 'zh': 'Chinese', 'ko': 'Korean'}
        nl = native_map.get(prompt_lang, prompt_lang)
        # The LLM speaks in stable character semantics only. Model-specific
        # expressions, motions and Cubism bindings stay behind the resolver.
        presentation_emotions = ", ".join(sorted(EMOTIONS))
        presentation_behaviors = ", ".join(sorted(BEHAVIORS - {"idle"}))

        format_instruction = (
            '\n[Output Instructions]\n'
            f'1. LANGUAGE: Write all text in {nl}. Every "text" field MUST be in {nl}.\n'
            '2. Keep your response SHORT — 1-2 sentences max, or a single brief paragraph.\n'
            '3. All JSON keys MUST be in English.\n'
            '4. Return ONLY valid JSON, no commentary.\n'
            '5. Format: {"segments":[{"text":"...","emotion":"neutral","behavior":"speak","attention":"user","energy":0.5,"intensity":0.5,"naturalVAD":{"valence":0,"arousal":0,"dominance":0},"contextTags":[]}],"tool_calls":[],"final_reply":"..."}\n'
            '5a. Never output Param*, Cubism IDs, parameter values, keyframes, or animation files.\n'
            f'6. Every final segment MUST set an "emotion" from: {presentation_emotions}.\n'
            f'7. Every final segment MUST set a semantic "behavior" from: {presentation_behaviors}. Use "speak" for an ordinary spoken reply; use greet/agree/disagree/think only when they fit.\n'
            '8. Never use idle for a segment that contains spoken text.\n'
            '9. Leave tool_calls as [] when not needed.\n'
            '10. Do NOT use [keyword] tags for emotions — use the "emotion" field in JSON segments instead.\n'
            '11. Do not output model names, expression files, motion names, Cubism IDs, bindings, or implementation details.\n'
        )
        messages.append({"role": "system", "content": format_instruction})

        # 5. Current user input
        user_text = ctx.user_text or ctx.event.payload.get("text", "")
        if user_text and ctx.input_origin == "initiative":
            initiative = ctx.initiative
            messages.append({
                "role": "system",
                "content": (
                    "Trusted initiative event (not a user message):\n"
                    f"{user_text}\nStructured event: {initiative}"
                ),
            })
        elif user_text:
            messages.append({"role": "user", "content": user_text})

        return Plan(messages=messages)


class Plan:
    def __init__(self, messages: list):
        self.messages = messages


class DecisionStep(Step):
    """Strategy combination: Planner → PromptCompiler → Reasoner.

    Calls the LLM, handles tool-calling loop (re-feeds tool results
    to the LLM for up to _MAX_TOOL_ROUNDS), then produces final reply.
    Adds turns to conversation history.

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
        if tool_supervisor is None:
            from app.runtime.tool_execution import ToolExecutionSupervisor
            tool_supervisor = ToolExecutionSupervisor(
                timeout_seconds=float(os.environ.get("TOOL_TIMEOUT_SECONDS", "20")),
                read_only_attempts=int(os.environ.get("TOOL_READ_ONLY_ATTEMPTS", "2")),
            )
        self.tool_supervisor = tool_supervisor

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

        response = LLMResponse()
        from app.interfaces.llm import LLMUsage
        accumulated_usage = LLMUsage()
        final_reply = ""

        for tool_round in range(_MAX_TOOL_ROUNDS):
            messages, round_budget = context_budget.fit_messages(messages)
            ctx.context_budget = round_budget
            response = await self.llm.generate(messages, tools=tool_schemas)
            accumulated_usage.add(response.usage)

            if response.error:
                final_reply = response.reply or ""
                break

            if not response.tool_calls:
                # No tool calls — this is the final response
                final_reply = response.reply
                break

            # Tool calls present — execute each tool
            if self.tools is None:
                final_reply = response.reply
                break

            # Use the full message list from the provider response
            if response.messages:
                messages = response.messages
            else:
                # Fallback: manually append assistant message with tool_calls
                assistant_msg = {"role": "assistant", "content": response.reply}
                tc_formatted = []
                for i, tc in enumerate(response.tool_calls):
                    tc_formatted.append({
                        "id": f"call_{tool_round}_{i}",
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": _json.dumps(tc.args, ensure_ascii=False),
                        },
                    })
                if tc_formatted:
                    assistant_msg["tool_calls"] = tc_formatted
                messages.append(assistant_msg)

            # Extract real tool_call IDs from the provider's assistant message
            real_tool_call_ids: list[str] = []
            if response.messages:
                last_msg = response.messages[-1]
                if last_msg.get("role") == "assistant" and "tool_calls" in last_msg:
                    real_tool_call_ids = [
                        tc.get("id", "") for tc in last_msg["tool_calls"]
                    ]

            # Execute each tool and append results
            for i, tc in enumerate(response.tool_calls):
                tc_name = tc.name
                tc_args = tc.args

                # Notify status callback before tool execution
                ctx.status_message = f"Executing tool: {tc_name}"
                if callable(ctx.status_callback):
                    await ctx.status_callback(ctx.status_message)

                schema_by_name = {
                    item.get("function", {}).get("name", ""): item
                    for item in (tool_schemas or [])
                }
                policy = ToolPolicy()
                risk = policy.risk_for(schema_by_name.get(tc_name))
                approved = risk == "read_only"
                if risk != "read_only" and callable(ctx.confirmation_callback):
                    approved = await ctx.confirmation_callback(
                        tc_name, tc_args, risk
                    )
                if approved:
                    execution = await self.tool_supervisor.execute(
                        self.tools, tc_name, tc_args, risk
                    )
                    result_text = execution.text
                    ctx.tool_audit.append(execution.audit)
                else:
                    result_text = (
                        '{"error":"confirmation_denied_or_required",'
                        f'"tool":"{tc_name}","risk":"{risk}"}}'
                    )
                    ctx.tool_audit.append({
                        "tool": tc_name, "risk": risk, "status": "denied",
                        "attempts": 0, "duration_ms": 0,
                        "argument_keys": sorted(str(key) for key in tc_args),
                    })
                result_text = policy.clean_result(result_text)
                result_text, tool_budget = context_budget.fit_tool_result(result_text)
                ctx.tool_result_budgets.append(tool_budget)

                # Detect screenshot JSON
                # NOTE: image_url content type is NOT sent because DeepSeek
                # (the current LLM backend) does not support vision input.
                # If switching to a vision-capable model (e.g. Claude),
                # restore the image_url content block here.
                tc_content: str | list = result_text
                try:
                    parsed = _json.loads(result_text)
                    if isinstance(parsed, dict) and parsed.get("type") == "screenshot":
                        w = parsed.get("width", 0)
                        h = parsed.get("height", 0)
                        tc_content = f"Screenshot captured ({w}x{h})"
                except (_json.JSONDecodeError, ValueError, TypeError):
                    pass  # plain text, use as-is

                tc_id = (
                    real_tool_call_ids[i]
                    if i < len(real_tool_call_ids)
                    else f"call_{tool_round}_{i}"
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": tc_content,
                })

            # Track tool calls in context state
            ctx.tool_calls.extend(
                {"name": tc.name, "args": tc.args}
                for tc in response.tool_calls
            )
            ctx.tool_results.append({
                "round": tool_round + 1,
                "tool_calls": [{"name": tc.name, "args": tc.args} for tc in response.tool_calls],
            })

            # Next round: LLM receives tool results
            messages, round_budget = context_budget.fit_messages(messages)
            ctx.context_budget = round_budget

        if not final_reply and response.tool_calls:
            messages.append({
                "role": "system",
                "content": (
                    "The tool-call budget is exhausted. Do not call more tools. "
                    "Use the available tool results to produce the final structured response now."
                ),
            })
            messages, round_budget = context_budget.fit_messages(messages)
            ctx.context_budget = round_budget
            response = await self.llm.generate(messages, tools=None)
            accumulated_usage.add(response.usage)
            final_reply = response.reply

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
            last_tone = segments[-1].get("emotion", segments[-1].get("tone", ""))
            if last_tone:
                ctx.emotion = last_tone

        # Add turns to conversation
        conversation = ctx.conversation
        if conversation is not None:
            if user_text and ctx.input_origin == "user":
                conversation.add_turn("user", user_text)
            if ctx.reply_text:
                conversation.add_turn("assistant", ctx.reply_text)
