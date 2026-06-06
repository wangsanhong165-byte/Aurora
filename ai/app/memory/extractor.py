"""Memory extractor — LLM-based extraction of facts from conversation.

Runs in the background worker thread; never blocks the main conversation loop.
"""

from __future__ import annotations

import json
from typing import Any

from app.memory.long_term import MemoryCard


_EXTRACTION_PROMPT = """你是一个记忆提取助手。从以下对话中提取关键信息。

规则：
1. 提取用户提到的事实（姓名、偏好、计划、重要事件等）
2. 提取助手给用户的承诺或约定
3. 用一句话总结这段对话的主题
4. 如果没有任何有价值的信息，返回空列表

返回 JSON 格式：
{
  "facts": ["事实1", "事实2"],
  "summary": "一句话主题总结",
  "promises": ["承诺1"]
}

对话：
{conversation}
"""


class MemoryExtractor:
    """LLM-powered memory extraction from conversation turns.

    Usage:
        extractor = MemoryExtractor(llm_adapter)
        cards = extractor.extract(turns=[{"user": "...", "assistant": "..."}])
    """

    def __init__(self, llm_adapter: Any = None) -> None:
        self._adapter = llm_adapter

    def set_adapter(self, adapter: Any) -> None:
        self._adapter = adapter

    def extract(
        self,
        turns: list[dict[str, Any]],
        source: str = "conversation",
    ) -> list[MemoryCard]:
        """Extract memory cards from conversation turns.

        Args:
            turns: List of {"user": "...", "assistant": "..."} dicts.
            source: Label for the memory source.

        Returns:
            List of MemoryCard objects, or empty list if extraction fails.
        """
        if not turns or self._adapter is None:
            return self._extract_fallback(turns, source)

        conversation = _format_turns(turns)
        prompt = _EXTRACTION_PROMPT.replace("{conversation}", conversation)

        try:
            result = self._adapter.generate(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            content = result.get("content", "")
            parsed = _safe_parse_json(content)
        except Exception:
            return self._extract_fallback(turns, source)

        cards: list[MemoryCard] = []

        for fact_text in parsed.get("facts", [])[:5]:
            text = str(fact_text).strip()
            if text and len(text) > 2:
                cards.append(MemoryCard(
                    type="fact",
                    content=text,
                    importance=0.6,
                    confidence=0.8,
                    source=source,
                ))

        summary = str(parsed.get("summary", "")).strip()
        if summary and len(summary) > 3:
            cards.append(MemoryCard(
                type="summary",
                content=summary,
                importance=0.5,
                confidence=0.7,
                source=source,
            ))

        for promise_text in parsed.get("promises", [])[:3]:
            text = str(promise_text).strip()
            if text and len(text) > 2:
                cards.append(MemoryCard(
                    type="promise",
                    content=text,
                    importance=0.8,
                    confidence=0.8,
                    source=source,
                ))

        return cards

    def _extract_fallback(
        self,
        turns: list[dict[str, Any]],
        source: str,
    ) -> list[MemoryCard]:
        """Heuristic fallback when no LLM adapter is available."""
        cards: list[MemoryCard] = []
        for turn in turns[-3:]:
            reply_memory = turn.get("memory", {})
            if isinstance(reply_memory, dict):
                for fact in reply_memory.get("facts", [])[:3]:
                    text = str(fact).strip()
                    if text:
                        cards.append(MemoryCard(
                            type="fact",
                            content=text,
                            importance=0.5,
                            confidence=0.6,
                            source=source,
                        ))
                summary = str(reply_memory.get("summary", "")).strip()
                if summary:
                    cards.append(MemoryCard(
                        type="summary",
                        content=summary,
                        importance=0.4,
                        confidence=0.5,
                        source=source,
                    ))
        return cards


def _format_turns(turns: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for t in turns[-10:]:
        user = str(t.get("user", "")).strip()
        assistant = str(t.get("assistant", "")).strip()
        if user:
            lines.append(f"用户: {user}")
        if assistant:
            lines.append(f"助手: {assistant}")
    return "\n".join(lines)


def _safe_parse_json(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    # Try extracting from markdown code block
    if "```json" in content:
        block = content.split("```json")[1].split("```")[0]
        try:
            return json.loads(block)
        except json.JSONDecodeError:
            pass
    if "{" in content and "}" in content:
        start = content.find("{")
        end = content.rfind("}") + 1
        try:
            return json.loads(content[start:end])
        except json.JSONDecodeError:
            pass
    return {}
