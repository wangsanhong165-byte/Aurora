"""AgentRuntime  OpenAI-compatible tool_calls loop with multi-step execution."""
from __future__ import annotations

import json
import os
import time
from typing import Any

from app.character.registry import CharacterRegistry
from app.tools.registry import ToolRegistry, Tool
from app.tools.builtins.screen import _register_all as _register_builtins
from app.brain.prompt_builder import PromptBuilder


_MAX_TOOL_ROUNDS = int(os.environ.get("AGENT_MAX_TOOL_ROUNDS", "5"))


class AgentRuntime:
    """Core runtime: character + tools + LLM tool_calls loop."""

    def __init__(
        self,
        character: CharacterRegistry | None = None,
        tools: ToolRegistry | None = None,
    ) -> None:
        self.character = character or CharacterRegistry()
        self.tools = tools or ToolRegistry()
        self.prompt_builder = PromptBuilder(self.character)
        _register_builtins(self.tools)

    # ---- system prompt ---------------------------------------------------
    def build_system(self, screen_context: str = "", user_query: str = "") -> str:
        """Build system prompt from active character card.

        Args:
            screen_context: Current screen/app context.
            user_query: Current user input for memory retrieval.
        """
        return self.prompt_builder.build(
            screen_context=screen_context,
            user_query=user_query,
        )

    # ---- tool_calls loop -------------------------------------------------
    def run(
        self,
        client: Any = None,
        model: str = "",
        user_text: str = "",
        history: list[dict[str, str]] | None = None,
        screen_context: str = "",
        temperature: float = 0.3,
        llm_adapter: Any = None,
    ) -> dict[str, Any]:
        t0 = time.time()
        system = self.build_system(screen_context=screen_context, user_query=user_text)

        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_text})

        tool_schemas = self.tools.list_openai_schemas()

        if llm_adapter is not None:
            return self._run_with_adapter(llm_adapter, messages, tool_schemas, temperature, t0)

        if client is None:
            return {"segments": [], "final_reply": "", "tool_rounds": 0, "elapsed": 0.0, "error": "No LLM client or adapter"}
        model = model or os.environ.get("LLM_MODEL", "")
        return self._run_legacy(client, model, messages, tool_schemas, temperature, t0)

    def _run_legacy(self, client, model, messages, tool_schemas, temperature, t0):
        rounds = 0
        while rounds < _MAX_TOOL_ROUNDS:
            rounds += 1
            kwargs = {"model": model, "messages": messages, "temperature": temperature}
            if tool_schemas:
                kwargs["tools"] = tool_schemas
            resp = client.chat.completions.create(**kwargs)
            msg = resp.choices[0].message
            if msg.tool_calls:
                messages.append({"role": "assistant", "content": msg.content, "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in msg.tool_calls]})
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    result = self.tools.execute(tc.function.name, args)
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                continue
            parsed = _parse_llm_content(msg.content or "")
            return {"segments": parsed.get("segments", []), "final_reply": parsed.get("final_reply", ""), "tool_rounds": rounds, "elapsed": time.time() - t0}
        return {"segments": [], "final_reply": "", "tool_rounds": rounds, "elapsed": time.time() - t0}

    def _run_with_adapter(self, llm_adapter, messages, tool_schemas, temperature, t0):
        rounds = 0
        while rounds < _MAX_TOOL_ROUNDS:
            rounds += 1
            result = llm_adapter.generate(messages, temperature=temperature, tools=tool_schemas or None, max_tool_rounds=1)
            tool_calls = result.get("tool_calls", [])
            if tool_calls and tool_schemas:
                raw_msg = result.get("raw_message")
                if raw_msg and hasattr(raw_msg, "tool_calls") and raw_msg.tool_calls:
                    messages.append({"role": "assistant", "content": raw_msg.content, "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in raw_msg.tool_calls]})
                else:
                    messages.append({"role": "assistant", "content": result.get("content", ""), "tool_calls": [{"id": f"call_{rounds}_{i}", "type": "function", "function": {"name": tc["name"], "arguments": json.dumps(tc.get("args", {}), ensure_ascii=False)}} for i, tc in enumerate(tool_calls)]})
                for i, tc in enumerate(tool_calls):
                    tool_result = self.tools.execute(tc["name"], tc.get("args", {}))
                    messages.append({"role": "tool", "tool_call_id": f"call_{rounds}_{i}", "content": tool_result})
                continue
            parsed = _parse_llm_content(result.get("content", ""))
            return {"segments": parsed.get("segments", []), "final_reply": parsed.get("final_reply", ""), "tool_rounds": rounds, "elapsed": time.time() - t0}
        return {"segments": [], "final_reply": "", "tool_rounds": rounds, "elapsed": time.time() - t0}

    def __repr__(self) -> str:
        return f"AgentRuntime(character={self.character.active_id!r})"


def _parse_llm_content(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    if "```json" in content:
        try:
            return json.loads(content.split("```json")[1].split("```")[0])
        except (json.JSONDecodeError, IndexError):
            pass
    if "{" in content and "}" in content:
        try:
            return json.loads(content[content.find("{"):content.rfind("}") + 1])
        except json.JSONDecodeError:
            pass
    return {"segments": [], "final_reply": content}
