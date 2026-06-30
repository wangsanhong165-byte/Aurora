"""DecisionStep — replaces the old Brain.

Composes: Planner → PromptCompiler → LLM.generate → ResponseParser

DecisionStep is protocol-agnostic. It consumes LLMResponse canonical
objects — no json.loads, no provider detection, no nested parsing.
All provider-specific normalization happens inside the provider layer.
"""

import logging
import os
from typing import Any

logger = logging.getLogger("decision_step")

from app.runtime.pipeline import Step
from app.runtime.context import Context
from app.interfaces.llm import LLMInterface, LLMResponse
from app.interfaces.tool import ToolInterface

_MAX_TOOL_ROUNDS = int(os.environ.get("AGENT_MAX_TOOL_ROUNDS", "5"))


class DefaultPlanner:
    """Build message list from character, memories, conversation, and user input."""

    def plan(self, ctx: Context) -> "Plan":
        messages: list[dict[str, str]] = []

        # 1. System prompt from character
        character = ctx.state.get("character")
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
        memories = ctx.state.get("memories", [])
        if memories:
            memory_parts = []
            compiled_memory = ""

            for m in memories[-10:]:
                mtype = m.get("type", "") if isinstance(m, dict) else ""
                data = m.get("data", {}) if isinstance(m, dict) else {}

                if mtype == "compiled":
                    compiled_memory = data.get("content", "")
                elif mtype == "fact":
                    fact = data.get("fact", "")
                    if fact:
                        memory_parts.append(f"[Fact] {fact}")
                elif mtype == "log":
                    content = data.get("content", "")
                    role = data.get("role", "")
                    if content and role:
                        label = "User" if role == "user" else "Assistant"
                        memory_parts.append(f"{label}: {content[:200]}")
                else:
                    # Legacy format (MockMemory conversation turns)
                    user = data.get("user", "")
                    assistant = data.get("assistant", "")
                    if user and assistant:
                        memory_parts.append(f"User said: {user}\nYou said: {assistant}")

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
        conversation = ctx.state.get("conversation")
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

        # 4. Output format instructions
        if character is not None:
            card = character.raw_card if hasattr(character, 'raw_card') else {}
            if isinstance(card, dict):
                tts_cfg = card.get('tts', {})
                prompt_lang = tts_cfg.get('prompt_lang', 'ja')
                tone_words = card.get('rules', {}).get('tone_words', ['neutral'])
            else:
                prompt_lang = 'ja'
                tone_words = ['neutral']
        else:
            prompt_lang = 'ja'
            tone_words = ['neutral']

        native_map = {'en': 'English', 'ja': 'Japanese', 'zh': 'Chinese', 'ko': 'Korean'}
        nl = native_map.get(prompt_lang, prompt_lang)
        first_tone = tone_words[0] if tone_words else 'neutral'

        format_instruction = (
            '\n[Output Instructions]\n'
            f'1. LANGUAGE LOCK: You MUST respond in {nl} only. Never use Chinese or any other language — even if the user writes in another language.\n'
            f'2. Every "text" field MUST contain {nl} text only.\n'
            '3. Return ONLY valid JSON, no commentary.\n'
            f'4. Format: {{"segments":[{{"text":"...","tone":"{first_tone}","gesture":"none"}}],"tool_calls":[],"final_reply":"..."}}\n'
            f'5. tone controls facial expression. Valid tones: {", ".join(tone_words)}\n'
            '6. gesture values: "none"(default), "wave", "tilt", "nod", "shrug"\n'
            '7. Leave tool_calls as [] when not needed.\n'
        )
        messages.append({"role": "system", "content": format_instruction})

        # 5. Current user input
        user_text = ctx.user_text or ctx.event.payload.get("text", "")
        if user_text:
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
    ):
        self.llm = llm
        self.tools = tool_provider
        self.planner = planner or DefaultPlanner()

    async def run(self, ctx: Context) -> None:
        plan = self.planner.plan(ctx)
        messages = list(plan.messages)

        user_text = ctx.user_text or ctx.event.payload.get("text", "")

        # Resolve tool schemas once, before the loop
        tool_schemas: list[dict] | None = None
        if self.tools is not None:
            try:
                tool_schemas = await self.tools.list_tools()
            except Exception:
                logger.warning("Failed to list tools — tool calling disabled")

        response = LLMResponse()
        final_reply = ""

        for tool_round in range(_MAX_TOOL_ROUNDS):
            response = await self.llm.generate(messages, tools=tool_schemas)

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
                            "arguments": str(tc.args),
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
            import json as _json

            for i, tc in enumerate(response.tool_calls):
                tc_name = tc.name
                tc_args = tc.args

                # Notify status callback before tool execution
                ctx.status_message = f"Executing tool: {tc_name}"
                if callable(ctx.status_callback):
                    await ctx.status_callback(ctx.status_message)

                try:
                    result_text = await self.tools.execute(tc_name, tc_args)
                except Exception as exc:
                    result_text = f"Error: {exc}"
                tc_id = (
                    real_tool_call_ids[i]
                    if i < len(real_tool_call_ids)
                    else f"call_{tool_round}_{i}"
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": result_text,
                })

            # Track tool calls in context state
            ctx.state.setdefault("tool_calls", []).extend(
                {"name": tc.name, "args": tc.args}
                for tc in response.tool_calls
            )
            ctx.state.setdefault("tool_results", []).append({
                "round": tool_round + 1,
                "tool_calls": [{"name": tc.name, "args": tc.args} for tc in response.tool_calls],
            })

            # Next round: LLM receives tool results

        ctx.reply_text = final_reply or response.reply

        # Extract segments from the final LLM response
        segments = response.segments or []
        if segments:
            ctx.segments = segments
            last_tone = segments[-1].get("tone", "")
            if last_tone:
                ctx.emotion = last_tone

        # Add turns to conversation
        conversation = ctx.state.get("conversation")
        if conversation is not None:
            if user_text:
                conversation.add_turn("user", user_text)
            if ctx.reply_text:
                conversation.add_turn("assistant", ctx.reply_text)
