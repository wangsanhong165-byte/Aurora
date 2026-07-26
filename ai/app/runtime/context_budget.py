"""Soft context budgets that protect high-value context."""

from __future__ import annotations

import os
from typing import Any


class ContextBudget:
    def __init__(
        self, soft_tokens: int | None = None, hard_tokens: int | None = None,
        tool_result_soft_chars: int = 8000, tool_result_hard_chars: int = 20000,
    ):
        self.soft_tokens = soft_tokens or int(os.getenv("LLM_CONTEXT_SOFT_TOKENS", "12000"))
        self.hard_tokens = hard_tokens or int(os.getenv("LLM_CONTEXT_HARD_TOKENS", "24000"))
        self.tool_result_soft_chars = tool_result_soft_chars
        self.tool_result_hard_chars = tool_result_hard_chars

    @staticmethod
    def estimate_tokens(text: str) -> int:
        cjk = sum(1 for char in text if "\u3400" <= char <= "\u9fff")
        return max(1, round(cjk * 0.6 + (len(text) - cjk) * 0.3))

    def fit_messages(self, messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict]:
        fitted = [dict(message) for message in messages]
        compacted = 0
        token_counts = [
            self.estimate_tokens(str(message.get("content", "")))
            for message in fitted
        ]
        total_tokens = sum(token_counts)
        while total_tokens > self.soft_tokens:
            removable = next((
                i for i, msg in enumerate(fitted[:-1])
                if msg.get("role") in {"user", "assistant"}
            ), None)
            if removable is None:
                break
            fitted.pop(removable)
            total_tokens -= token_counts.pop(removable)
            compacted += 1
        if total_tokens > self.hard_tokens:
            # Absolute anomaly guard. Prefer trimming tool and low-priority
            # system context, but eventually cap every oversized component.
            while total_tokens > self.hard_tokens:
                candidates = [
                    (self.estimate_tokens(str(msg.get("content", ""))), i)
                    for i, msg in enumerate(fitted[:-1])
                    if len(str(msg.get("content", ""))) > 64
                ]
                if not candidates:
                    break
                _, index = max(candidates)
                content = str(fitted[index].get("content", ""))
                excess = total_tokens - self.hard_tokens
                cut_chars = max(128, int(excess / 0.3))
                new_length = max(64, len(content) - cut_chars)
                fitted[index]["content"] = (
                    content[:new_length]
                    + "\n[context truncated by hard safety limit]"
                )
                new_tokens = self.estimate_tokens(str(fitted[index]["content"]))
                if new_tokens >= token_counts[index] and len(fitted) > 3:
                    total_tokens -= token_counts.pop(index)
                    fitted.pop(index)
                    compacted += 1
                    continue
                if new_tokens >= token_counts[index]:
                    break
                total_tokens += new_tokens - token_counts[index]
                token_counts[index] = new_tokens
        return fitted, {
            "estimated_tokens": total_tokens,
            "compacted_messages": compacted,
            "soft_tokens": self.soft_tokens,
            "hard_tokens": self.hard_tokens,
        }

    def fit_tool_result(self, content: str) -> tuple[str, dict]:
        if len(content) <= self.tool_result_soft_chars:
            return content, {"truncated": False, "original_chars": len(content)}
        if len(content) <= self.tool_result_hard_chars:
            head = max(1, self.tool_result_soft_chars * 3 // 4)
            tail = max(1, self.tool_result_soft_chars - head)
            value = (
                content[:head] + "\n[tool result compacted]\n" + content[-tail:]
            )
            return value, {
                "truncated": False, "compacted": True,
                "original_chars": len(content),
            }
        keep = max(1, self.tool_result_hard_chars - 48)
        value = content[:keep] + "\n[tool result truncated by hard safety limit]"
        return value, {
            "truncated": True, "compacted": True,
            "original_chars": len(content),
        }
