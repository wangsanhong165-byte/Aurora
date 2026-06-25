"""PromptBuilder — constructs system prompts from character cards + compiled memory.

Builds: character setting + screen context + compiled memory + conversation context
+ output format instructions.

Memory section reads from per-character compiled memory (memory/compiled/{char_id}/memory.md).
Supports any character persona — all labels use the character's actual name.
"""

from __future__ import annotations
from typing import Any

from app.memory.store import memory_store


class PromptBuilder:
    """Builds system prompts from character cards and compiled memory context."""

    def __init__(self, character_registry: Any) -> None:
        self.character = character_registry

    # ── helpers ────────────────────────────────────────────────────

    def _char_name(self) -> str:
        """Get the active character's display name."""
        try:
            card = self.character.active
            return card.get("name", {}).get("zh", card.get("id", "AI"))
        except Exception:
            return "AI"

    def _char_id(self) -> str:
        try:
            return self.character.active_id or ""
        except Exception:
            return ""

    def _get_compiled_memory(self) -> str:
        """Get per-character compiled memory."""
        from app.memory.compiler import get_compiled_memory
        return get_compiled_memory(self._char_id())

    # ── build ──────────────────────────────────────────────────────

    def build(
        self,
        screen_context: str = "",
        include_tool_instruction: bool = True,
        user_query: str = "",
        memory_k: int = 5,
    ) -> str:
        """Build system prompt from character card + compiled memory + context."""
        card = self.character.active
        char_name = self._char_name()

        setting = card.get("character_setting", "")
        if not setting:
            sp = card.get("system_prompt", "")
            base = (
                sp.get("zh") or sp.get("ja") or str(sp)
                if isinstance(sp, dict) else str(sp)
            )
        else:
            base = str(setting)

        sections: list[str] = [base]

        # ── screen context ────────────────────────────────────────
        if screen_context:
            sections.append("\n[屏幕上下文]\n" + screen_context)

        # ── compiled memory (per-character) ───────────────────────
        compiled = self._get_compiled_memory()
        if compiled:
            sections.append("\n[记忆]\n" + compiled)
        else:
            # Fallback: old per-fact lookup during transition
            if user_query:
                context = memory_store.build_prompt_context(
                    query=user_query, max_recent_turns=3, max_facts=memory_k,
                )
                if context:
                    sections.append(context)

        # ── recent conversation context ───────────────────────────
        recent = memory_store.recent_turns(5)
        if recent:
            lines = ["\n[最近对话]"]
            for t in recent:
                content = str(t.get("content", "")).strip()
                role = t.get("role", "user")
                if content:
                    lines.append(f"{'用户' if role == 'user' else char_name}: {content[:200]}")
            sections.append("\n".join(lines))

        # ── output format instructions ────────────────────────────
        if include_tool_instruction:
            tts_cfg = card.get('tts', {})
            prompt_lang = tts_cfg.get('prompt_lang', 'ja')
            native = {'en': 'English', 'ja': '日本語', 'ko': '한국어', 'zh': '中文'}
            if prompt_lang not in native:
                native[prompt_lang] = prompt_lang
            nl = native.get(prompt_lang, prompt_lang)
            lc = {'en': 'en', 'ja': 'ja', 'ko': 'ko'}.get(prompt_lang, 'ja')
            r = card.get('rules', {})
            tones = ', '.join(r.get('tone_words', ['neutral']))
            ft = list(r.get('tone_words', ['neutral']))[0]

            sections.append(
                '\n[语言 - 输出格式]\n'
                + '1. 用 ' + nl + ' 输出主要文本\n'
                + '2. 每个 segment 的 "' + lc + '" 字段写 ' + nl + ' 文本\n'
                + '3. 每个 segment 的 "zh" 字段写中文翻译\n'
                + '4. final_reply 写中文版本\n'
                + '5. 不要输出任何其他解释性文字\n'
                + '6. 用户说中文时你也要用主要语言回复，zh 字段才是中文\n'
            )
            sections.append(
                '\n[输出格式]\n'
                + '返回 JSON 格式回复:\n'
                + '{"segments":[{"' + lc + '":"...","zh":"...","tone":"' + ft + '","gesture":"none"}],"tool_calls":[],"final_reply":"..."}\n'
                + '8. gesture values: \"none\"(default), \"wave\", \"tilt\", \"nod\", \"shrug\"\n'
                + '9. tone controls facial expression index, gesture controls body motion\n'
                + '10. IMPORTANT: You have a Live2D body visible to users. Use gestures naturally.\n'
                + '11. IMPORTANT: Do NOT use emoji, kaomoji, or colloquial filler words.\n'
                + '不需要 tool_calls 时填 []\n'
            )
        return '\n\n'.join(section for section in sections if section.strip())

    def build_initiative_prompt(
        intent_type: str, topic: str,
        activity: str = "", app_name: str = "",
    ) -> str:
        """Build initiative prompt — direct, natural, no meta-explanation."""
        labels = {
            "follow_up": "跟进",
            "curiosity": "好奇",
            "care": "关心",
            "presence_check": "问候",
            "share_thought": "分享想法",
        }
        label = labels.get(intent_type, intent_type)

        parts = ["[主动对话 - 发起对话的缘由]"]
        parts.append(f"要提及的话题: {topic}")
        if activity:
            al = {"coding": "在写代码", "writing": "在写作",
                  "gaming": "在玩游戏", "browsing": "在浏览网页",
                  "chatting": "在聊天"}
            a = al.get(activity, "在" + (app_name or activity))
            parts.append(f"用户状态: {a}")
        parts.append("")
        parts.append("规则:")
        parts.append("- 自然说话，像你自己想说的那样")
        parts.append("- 不要提到系统提示或'被激活'")
        parts.append("- 1-2句话，温暖自然")
        parts.append("- 用标准双语 JSON 格式输出")
        return "\n".join(parts)



