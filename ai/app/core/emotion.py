"""Emotion tracker  infers emotional state from conversation and context.

Updates RuntimeState.emotion automatically. Never calls LLM directly.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone


_POSITIVE = [
    "哈哈", "开心", "太棒", "真好", "喜欢", "谢谢", "cool", "great", "awesome",
    "nice", "love", "wonderful", "excellent", "good", "happy", "yeah", "yay",
    "太好了", "不错", "厉害", "牛", "好看", "好听", "好玩", "有趣", "好开心",
]
_NEGATIVE = [
    "烦", "累", "难过", "生气", "讨厌", "糟糕", "sad", "angry", "bad",
    "terrible", "hate", "awful", "frustrated", "tired", "exhausted",
    "好累", "烦死了", "无语", "崩溃", "不想", "没意思", "无聊",
    "不好", "不行", "失败", "错了", "太难", "不舒服",
]
_SURPRISED = [
    "啊", "哇", "天哪", "不是吧", "真的假的", "wow", "omg", "what",
    "unbelievable", "incredible", "真的吗", "不会吧", "竟然", "居然",
]
_THINKING = [
    "嗯", "让我想", "hmm", "maybe", "perhaps", "let me think",
    "我觉得", "可能", "应该", "考虑", "想想", "不确定",
]


def _time_emotion() -> str:
    hour = (datetime.now(timezone.utc).hour + 8) % 24
    if hour < 6:
        return "tired"
    elif hour < 9:
        return "neutral"
    elif hour < 12:
        return "energetic"
    elif hour < 14:
        return "neutral"
    elif hour < 18:
        return "focused"
    elif hour < 22:
        return "relaxed"
    else:
        return "tired"


class EmotionTracker:
    """Infers emotional state from text and time context."""

    def __init__(self, history_size: int = 5) -> None:
        self._history: list[str] = []
        self._history_size = history_size

    def infer(
        self,
        user_text: str = "",
        assistant_text: str = "",
        time_weight: float = 0.15,
    ) -> str:
        combined = f"{user_text} {assistant_text}".lower()

        scores: dict[str, float] = {
            "happy": self._score(combined, _POSITIVE),
            "sad": self._score(combined, _NEGATIVE),
            "surprised": self._score(combined, _SURPRISED) * 1.1,
            "thinking": self._score(combined, _THINKING) * 0.9,
        }

        time_emo = _time_emotion()
        for key in list(scores):
            scores[key] = scores[key] * (1 - time_weight) + (1.0 if key == time_emo else 0.0) * time_weight

        top_score = max(scores.values())
        if top_score <= time_weight + 0.05:
            emotion = time_emo
        else:
            emotion = max(scores, key=lambda k: scores[k])

        # Smooth
        self._history.append(emotion)
        if len(self._history) > self._history_size:
            self._history = self._history[-self._history_size:]

        recent = self._history[-3:] if len(self._history) >= 3 else self._history
        if len(set(recent)) == 1:
            return recent[0]
        return Counter(recent).most_common(1)[0][0]

    @staticmethod
    def _score(text: str, keywords: list[str]) -> float:
        count = sum(1 for kw in keywords if kw.lower() in text)
        return min(count / 3.0, 1.0)

    def reset(self) -> None:
        self._history.clear()


emotion_tracker = EmotionTracker()
