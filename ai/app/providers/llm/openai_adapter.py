"""OpenAILLMProvider — implements LLMInterface via OpenAI-compatible HTTP API.

Wraps the existing OpenAILLMAdapter (from app.models.http_adapters) into
the canonical LLMInterface. Handles sync-to-async bridge via asyncio.to_thread.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from app.interfaces.llm import LLMInterface, LLMResponse, LLMUsage, ToolCall
from app.models.http_adapters import OpenAILLMAdapter


class OpenAILLMProvider(LLMInterface):
    """Async wrapper around OpenAILLMAdapter for the CharacterTurn Runtime.

    Runs the synchronous OpenAILLMAdapter.generate() in a thread pool
    via asyncio.to_thread so the CharacterTurn pipeline stays async.

    Response normalization:
      The DefaultPlanner instructs the LLM to output structured JSON:
        {"segments":[...], "tool_calls":[...], "final_reply":"..."}
      This JSON lands in msg.content (the LLM's text output). This provider
      extracts final_reply, segments, and tool_calls from the nested JSON
      and returns a canonical LLMResponse — no JSON strings leak out.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self._adapter = OpenAILLMAdapter(
            api_key=api_key,
            base_url=base_url,
            model=model,
        )

    @property
    def model(self) -> str:
        return self._adapter.model

    async def generate(
        self,
        messages: list,
        tools: list[dict] | None = None,
        **kwargs,
    ) -> LLMResponse:
        """Call LLM and return a canonical LLMResponse.

        Runs the sync adapter in a thread to avoid blocking the event loop.
        Normalizes provider-specific response format into LLMResponse.
        """
        result = await asyncio.to_thread(
            self._adapter.generate,
            messages,
            temperature=kwargs.get("temperature", 0.3),
            tools=tools,
            max_tool_rounds=1,  # single round per call; loop handled by DecisionStep
        )

        return self._normalize(result, messages)

    def _normalize(
        self,
        result: dict[str, Any],
        original_messages: list,
    ) -> LLMResponse:
        """Convert raw adapter result dict into canonical LLMResponse.

        Handles:
          - Native OpenAI tool_calls (msg.tool_calls from SDK)
          - JSON-in-text structured output (per DefaultPlanner format)
          - Plain text fallback (no JSON in content)
        """
        # ── Extract tool_calls from native SDK mechanism ──────────────
        raw_tool_calls = result.get("tool_calls", [])
        tool_calls = [
            ToolCall(name=tc["name"], args=tc.get("args", {}))
            for tc in raw_tool_calls
        ]

        # ── Parse LLM text content ────────────────────────────────────
        content = result.get("content", "")
        segments: list[dict] = []
        # Only expose a transcript when the provider actually returned one.
        # JSON-in-text tool calls have no native assistant/tool_call message;
        # DecisionStep must synthesize that message before appending tool results.
        messages: list = result.get("_messages", [])
        reply = content
        reasoning = str(result.get("reasoning", "") or "")

        if content and content.strip().startswith("{"):
            try:
                inner = json.loads(content)

                # Extract reply text
                inner_reply = inner.get("final_reply", "")
                if inner_reply:
                    reply = inner_reply

                # Extract segments
                inner_segments = inner.get("segments")
                if inner_segments is not None:
                    segments = inner_segments

                # Extract JSON-in-text tool_calls as fallback
                inner_tool_calls = inner.get("tool_calls")
                if inner_tool_calls and not tool_calls:
                    tool_calls = [
                        ToolCall(name=tc.get("name", ""), args=tc.get("args", {}))
                        for tc in inner_tool_calls
                    ]

            except (json.JSONDecodeError, ValueError):
                pass  # content is plain text, use as-is

        raw_usage = result.get("usage") or {}
        cached = raw_usage.get("cached_tokens", 0)
        usage_details = raw_usage.get("prompt_tokens_details") or {}
        cached = cached or usage_details.get("cached_tokens", 0)
        return LLMResponse(
            reply=reply,
            reasoning=reasoning,
            segments=segments,
            tool_calls=tool_calls,
            messages=messages,
            usage=LLMUsage(
                prompt_tokens=int(raw_usage.get("prompt_tokens", 0) or 0),
                completion_tokens=int(raw_usage.get("completion_tokens", 0) or 0),
                total_tokens=int(raw_usage.get("total_tokens", 0) or 0),
                cached_tokens=int(cached or 0),
                model=str(result.get("model", "")),
            ),
        )

    async def generate_stream(
        self,
        messages: list,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Stream tokens from the LLM via the sync adapter's generator."""
        gen = self._adapter.generate_stream(
            messages,
            temperature=kwargs.get("temperature", 0.3),
        )
        loop = asyncio.get_running_loop()

        while True:
            try:
                token = await loop.run_in_executor(None, lambda: next(gen))
                yield token
            except StopIteration:
                break
