"""PromptBuilder  constructs system prompts from character cards.

Decoupled from AgentRuntime so Brain, initiative, and future callers
all build prompts consistently. Injects relevant long-term memories
when available.
"""

from __future__ import annotations

from typing import Any


class PromptBuilder:
    """Builds system prompts from character cards and context."""

    def __init__(self, character_registry: Any) -> None:
        self.character = character_registry

    def build(
        self,
        screen_context: str = "",
        include_tool_instruction: bool = True,
        user_query: str = "",
        memory_k: int = 5,
    ) -> str:
        """Build the full system prompt.

        Args:
            screen_context: Current screen/app context if available.
            include_tool_instruction: Whether to include JSON output format.
            user_query: Current user input, used to retrieve relevant memories.
            memory_k: Max number of memory cards to inject.

        Returns:
            Full system prompt string.
        """
        card = self.character.active

        setting = card.get("character_setting", "")
        if not setting:
            sp = card.get("system_prompt", "")
            base = (
                sp.get("zh") or sp.get("ja") or str(sp)
                if isinstance(sp, dict)
                else str(sp)
            )
        else:
            base = str(setting)

        rules = card.get("rules", {})
        tones = ", ".join(rules.get("tone_words", ["neutral"]))
        avoid = ", ".join(rules.get("avoid", []))

        sections = [base]

        # --- Inject relevant long-term memories ---
        if user_query:
            memories_text = self._get_relevant_memories(user_query, k=memory_k)
            if memories_text:
                sections.append(memories_text)

        # Output format instruction
        if include_tool_instruction:
            # Determine primary language from character card
            tts_cfg = card.get("tts", {})
            prompt_lang = tts_cfg.get("prompt_lang", "ja")
            lang_label, lang_code = {
                "en": ("English", "en"),
                "ja": ("日语", "ja"),
                "ko": ("韩语", "ko"),
            }.get(prompt_lang, ("日语", "ja"))
            sections.append(
                f"\n[输出格式]\n"
                f"请以 JSON 格式输出回复：\n"
                f'{{"segments":[{{"{lang_code}":"{lang_label}","zh":"中文","tone":"语气"}}],'
                f'"tool_calls":[{{"name":"工具名","args":{{}}}}],'
                f'"final_reply":"最终回复"}}\n'
                f"可用语气: {tones}\n"
                f"如果不调用工具，tool_calls 设为 []。"
            )

        if avoid:
            sections.append(f"\n[避免] {avoid}")

        if screen_context:
            sections.append(f"\n[当前屏幕内容]\n{screen_context}")

        return "\n".join(sections)

    def build_simple(self, screen_context: str = "") -> str:
        """Build a simple prompt without tool-calling instructions."""
        card = self.character.active
        setting = card.get("character_setting", "")
        if not setting:
            sp = card.get("system_prompt", "")
            base = (
                sp.get("zh") or sp.get("ja") or str(sp)
                if isinstance(sp, dict)
                else str(sp)
            )
        else:
            base = str(setting)

        rules = card.get("rules", {})
        avoid = ", ".join(rules.get("avoid", []))

        sections = [base]
        if avoid:
            sections.append(f"\n[避免] {avoid}")
        if screen_context:
            sections.append(f"\n[当前屏幕内容]\n{screen_context}")

        return "\n".join(sections)

    @staticmethod
    def _get_relevant_memories(query: str, k: int = 5) -> str:
        """Search VectorIndex and format relevant memories as prompt text."""
        try:
            from app.memory.vector_index import memory_index
            if not memory_index.built:
                return ""
            results = memory_index.search(query, k=k, min_score=0.05)
            if not results:
                return ""
            lines = ["\n[相关记忆]"]
            for r in results:
                card = r["card"]
                ctype = card.get("type", "fact")
                content = card.get("content", "")
                if content:
                    prefix = {"fact": "•", "summary": "§", "promise": "‼"}.get(ctype, "•")
                    lines.append(f"{prefix} {content}")
            return "\n".join(lines)
        except Exception:
            return ""
