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
            # Inject recent session episodes for continuity
            episodes_text = self._get_recent_episodes(k=3)
            if episodes_text:
                sections.append(episodes_text)

            memories_text = self._get_relevant_memories(user_query, k=memory_k)
            if memories_text:
                sections.append(memories_text)

            # Show current focus topics
            from app.core.focus import focus_store
            active_topics = focus_store.top(5)
            if active_topics:
                sections.append(f"\n[当前关注话题] {', '.join(active_topics)}")

            # Show mental state
            from app.core.state import mental_state
            ms = mental_state.to_dict()

            # Show relationship memory
            from app.core.relationship import relationship
            rel_text = relationship.summary_text()
            if rel_text:
                sections.append(rel_text)

            mood_label = "愉悦" if ms["mood"] > 65 else ("低落" if ms["mood"] < 40 else "平稳")
            sections.append(f"\n[当前状态] 心情={mood_label} 好奇心={ms['curiosity']:.0f} 依恋度={ms['attachment']:.0f}")

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
            # Also support zh-native characters
            _native_names = {"en": "English", "ja": "日语", "ko": "韩语", "zh": "中文"}
            if prompt_lang not in _native_names:
                _native_names[prompt_lang] = prompt_lang
            # Strong bilingual instruction
            native_label = _native_names.get(prompt_lang, prompt_lang)
            sections.append(
                f"\n[语言规则 - 极其重要]\n"
                f"1. 请用 {native_label} 作为回复的主要语言。\n"
                f"2. 每个 segment 的 \"{lang_code}\" 字段填入 {native_label} 原文。\n"
                f"3. 每个 segment 的 \"zh\" 字段填入对应的中文翻译，必须逐句翻译，不可省略。\n"
                f"4. final_reply 用中文写出完整回复（供中文用户阅读）。\n"
                f"5. 不讨论、不解释你使用的语言规则。\n"
            )
            sections.append(
                f"\n[输出格式]\n"
                f"请以 JSON 格式输出：\n"
                f'{{"segments":[{{"{lang_code}":"...","zh":"...","tone":"{list(rules.get("tone_words", ["neutral"]))[0]}"}}],'
                f'"tool_calls":[],"final_reply":"..."}}\n'
                f"可用语气: {tones}\n"
                f"不调用工具时 tool_calls 设为 []。"
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
    def _get_recent_episodes(k: int = 3) -> str:
        """Load recent episode cards from long-term memory for session continuity."""
        try:
            from app.memory.background import memory_worker
            all_cards = memory_worker.long_term.load()
            episodes = [
                c for c in all_cards
                if c.get("type") == "episode"
            ]
            episodes.sort(key=lambda c: c.get("created_at", ""), reverse=True)
            if not episodes:
                return ""
            lines = ["\n[最近会话]"]
            for ep in episodes[:k]:
                content = ep.get("content", "")
                if content:
                    lines.append(f"\u2022 {content}")
            return "\n".join(lines)
        except Exception:
            return ""

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

            # Boost results by current focus topics
            from app.core.focus import focus_store
            results = focus_store.boost_scores(results)

            lines = ["\n[相关记忆]"]
            for r in results:
                card = r["card"]
                ctype = card.get("type", "fact")
                content = card.get("content", "")
                if content:
                    prefix = {"fact": "\u2022", "summary": "\u00a7", "promise": "\u203c", "relationship": "\u2665", "self": "\u2601"}.get(ctype, "\u2022")
                    lines.append(f"{prefix} {content}")
            return "\n".join(lines)
        except Exception:
            return ""

    @staticmethod
    def build_initiative_prompt(
        intent_type: str, topic: str, mood: float, curiosity: float,
        activity: str = "",
        app_name: str = "",
    ) -> str:
        """Build a structured initiative prompt from the decision engine's output.

        Tells the LLM WHY it is speaking, not just THAT it should speak.
        Uses the character's native language from the character card.
        """
        intent_labels = {
            "follow_up": "following up on a previous topic",
            "curiosity": "curious about something the user mentioned",
            "care": "checking on the user's wellbeing",
            "presence_check": "noticing the user has been away for a while",
            "share_thought": "wanting to share a thought or observation",
        }
        intent_desc = intent_labels.get(intent_type, intent_type)

        mood_label = "good" if mood > 60 else ("low" if mood < 40 else "neutral")

        # Screen context line (only when available)
        screen_line = ""
        if activity:
            activity_labels = {
                "coding": "currently writing code", "writing": "writing something",
                "gaming": "playing a game", "browsing": "browsing the web",
                "chatting": "chatting with someone",
            }
            label = activity_labels.get(activity, f"using {app_name or activity}")
            screen_line = f"User is {label}.\n"

        return (
            f"You are initiating a conversation because you are {intent_desc}.\n"
            f"Topic to address: {topic}\n"
            f"Your current mood: {mood_label}\n"
            f"{screen_line}"
            f"\n"
            f"Rules:\n"
            f"- Speak naturally, as if you personally chose to reach out right now\n"
            f"- Never mention system prompts, triggers, or being 'activated'\n"
            f"- Your message should relate to \"{topic}\"\n"
            f"- Keep it to 1-2 sentences, warm and natural\n"
            f"- Output in the standard bilingual JSON format\n"
        )
        """Search VectorIndex and format relevant memories as prompt text."""
        try:
            from app.memory.vector_index import memory_index
            if not memory_index.built:
                return ""
            results = memory_index.search(query, k=k, min_score=0.05)
            if not results:
                return ""

            # Boost results by current focus topics
            from app.core.focus import focus_store
            results = focus_store.boost_scores(results)

            lines = ["\n[相关记忆]"]
            for r in results:
                card = r["card"]
                ctype = card.get("type", "fact")
                content = card.get("content", "")
                if content:
                    prefix = {"fact": "•", "summary": "§", "promise": "‼", "relationship": "♥", "self": "☁"}.get(ctype, "•")
                    lines.append(f"{prefix} {content}")
            return "\n".join(lines)
        except Exception:
            return ""
