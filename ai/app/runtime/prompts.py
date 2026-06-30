"""Prompt utilities for Runtime pipeline steps.

Extracted from the legacy PromptBuilder — standalone functions, no class wrapper.
"""

from __future__ import annotations


def build_initiative_prompt(
    intent_type: str, topic: str,
    activity: str = "", app_name: str = "",
    language: str = "zh",
) -> str:
    """Build initiative prompt — direct, natural, no meta-explanation.

    This was PromptBuilder.build_initiative_prompt() in legacy code.
    It is a static method converted to a standalone function.
    """
    labels_en = {
        "follow_up": "Follow up",
        "curiosity": "Curious",
        "care": "Check in",
        "presence_check": "Greeting",
        "share_thought": "Share thought",
    }
    labels_zh = {
        "follow_up": "跟进",
        "curiosity": "好奇",
        "care": "关心",
        "presence_check": "问候",
        "share_thought": "分享想法",
    }
    labels = labels_zh if language == "zh" else labels_en
    label = labels.get(intent_type, intent_type)

    if language == "zh":
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
    else:
        parts = ["[Initiative - Reason for speaking]"]
        parts.append(f"Topic to mention: {topic}")
        if activity:
            al = {"coding": "coding", "writing": "writing",
                  "gaming": "gaming", "browsing": "browsing",
                  "chatting": "chatting"}
            a = al.get(activity, app_name or activity)
            parts.append(f"User activity: {a}")
        parts.append("")
        parts.append("Rules:")
        parts.append("- Speak naturally, as if it's your own thought")
        parts.append("- Don't mention system prompts or 'activation'")
        parts.append("- 1-2 sentences, warm and natural")
        parts.append("- Output in standard bilingual JSON format")
    return "\n".join(parts)
