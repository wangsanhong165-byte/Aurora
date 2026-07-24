"""Bounded, deduplicated memory context for the LLM."""

from __future__ import annotations


class ContextAssembler:
    def assemble_memories(
        self, memories: list[dict], *, total_chars: int = 6000
    ) -> tuple[str, list[str]]:
        compiled = ""
        relevant: list[str] = []
        seen: set[str] = set()
        used = 0
        for memory in reversed(memories[-10:]):
            if not isinstance(memory, dict):
                continue
            kind = memory.get("type", "")
            data = memory.get("data", {})
            if kind == "compiled":
                text = str(data.get("content", ""))[:3000]
                if text and not compiled:
                    compiled = text
                    used += len(text)
                continue
            if kind == "fact":
                fact = " ".join(str(data.get("fact", "")).split())
                text = f"[Fact] {fact}".strip()
            elif kind == "log":
                role = data.get("role", "")
                label = "User" if role == "user" else "Assistant"
                text = f"{label}: {str(data.get('content', ''))[:300]}"
            else:
                user, assistant = data.get("user", ""), data.get("assistant", "")
                text = f"User said: {user}\nYou said: {assistant}" if user and assistant else ""
            key = " ".join(text.lower().split())
            if not text or key in seen or used + len(text) > total_chars:
                continue
            seen.add(key)
            relevant.append(text)
            used += len(text)
        relevant.reverse()
        return compiled, relevant
