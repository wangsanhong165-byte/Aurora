"""PromptBuilder constructs system prompts from character cards.

Builds: character setting + conversation context + relevant memories
+ output format. No mood/emotion/metrics injected.
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
        """Build system prompt from character card + context.
        No mood/emotion/metrics - LLM infers these naturally from history."""
        card = self.character.active
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

        if screen_context:
            sections.append("\n[屏幕上下文]\n" + screen_context)

        if user_query:
            from app.memory.store import memory_store
            context = memory_store.build_prompt_context(
                query=user_query, max_recent_turns=3, max_facts=memory_k,
            )
            if context:
                sections.append(context)

        if include_tool_instruction:
            tts_cfg = card.get('tts', {})
            prompt_lang = tts_cfg.get('prompt_lang', 'ja')
            native = {'en': 'English', 'ja': '日本語', 'ko': '한국어', 'zh': '中文'}
            if prompt_lang not in native:
                native[prompt_lang] = prompt_lang
            nl = native.get(prompt_lang, prompt_lang)
            lc = {'en':'en','ja':'ja','ko':'ko'}.get(prompt_lang, 'ja')
            r = card.get('rules', {})
            tones = ', '.join(r.get('tone_words', ['neutral']))
            ft = list(r.get('tone_words', ['neutral']))[0]

            sections.append(
                '\n[语言 - 输出格式]\n'
                + '1. \u7528 ' + nl + ' \u8f93\u51fa\u4e3b\u8981\u6587\u672c\n'
                + '2. \u6bcf\u4e2a segment \u7684 \"' + lc + '\" \u5b57\u6bb5\u5199 ' + nl + ' \u6587\u672c\n'
                + '3. \u6bcf\u4e2a segment \u7684 \"zh\" \u5b57\u6bb5\u5199\u4e2d\u6587\u7ffb\u8bd1\n'
                + '4. final_reply \u5199\u4e2d\u6587\u7248\u672c\n'
                + '5. \u4e0d\u8981\u8f93\u51fa\u4efb\u4f55\u5176\u4ed6\u89e3\u91ca\u6027\u6587\u5b57\n'
            )
            sections.append(
                '\n[输出格式]\n'
                + '返回 JSON 格式回复:\n'
                + '{"segments":[{"' + lc + '":"...","zh":"...","tone":"' + ft + '"}],"tool_calls":[],"final_reply":"..."}\n'
                + '可用情绪: ' + tones + '\n'
                + '不需要 tool_calls 时填 []\n'
            )

        return '\n\n'.join(section for section in sections if section.strip())

    @staticmethod
    def build_initiative_prompt(
        intent_type: str, topic: str,
        activity: str = "", app_name: str = "",
    ) -> str:
        """Build initiative prompt - direct, natural, no meta-explanation."""
        labels = {
            "follow_up": "??",
            "curiosity": "??",
            "care": "??",
            "presence_check": "??",
            "share_thought": "??",
        }
        label = labels.get(intent_type, intent_type)

        parts = ["[主动对话 - 发起对话的缘由]"]
        parts.append(f"要提及的话题: {topic}")
        if activity:
            al = {"coding":"在写代码","writing":"在写作",
                  "gaming":"在玩游戏","browsing":"在浏览网页",
                  "chatting":"在聊天"}
            a = al.get(activity, "??" + (app_name or activity))
            parts.append(f"用户状态: {a}")
        parts.append("")
        parts.append("规则:")
        parts.append("- 自然说话，像你自己想说的那样")
        parts.append("- 不要提到系统提示或'被激活'")
        parts.append("- 1-2句话，温暖自然")
        parts.append("- 用标准双语 JSON 格式输出")
        return "\n".join(parts)
