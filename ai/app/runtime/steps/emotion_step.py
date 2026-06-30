"""EmotionStep — analyze reply text and update character emotion."""

from app.runtime.pipeline import Step
from app.runtime.context import Context


# Keyword → emotion mapping for lightweight analysis
_POSITIVE_WORDS = {
    "happy", "glad", "great", "love", "wonderful", "amazing", "awesome",
    "nice", "good", "beautiful", "fantastic", "excellent", "joy", "fun",
    "哈哈", "开心", "太棒", "真好", "喜欢", "太好了", "不错",
}

_SAD_WORDS = {
    "sad", "sorry", "miss", "miss you", "lonely", "cry", "unfortunate",
    "难过", "伤心", "可惜", "想念", "孤独", "哭",
}

_ANGRY_WORDS = {
    "angry", "mad", "furious", "annoying", "hate", "terrible",
    "生气", "烦", "讨厌", "可恶", "愤怒",
}

_SURPRISED_WORDS = {
    "wow", "really?", "oh", "surprising", "unexpected", "incredible",
    "真的吗", "哇", "天哪", "不会吧", "竟然",
}


def _detect_emotion(text: str) -> str:
    """Simple keyword-based emotion detection.

    Returns one of EmotionState.VALID_EMOTIONS.
    """
    lower = text.lower()

    # Count hits per emotion category
    scores = {
        "happy": sum(1 for w in _POSITIVE_WORDS if w in lower),
        "sad": sum(1 for w in _SAD_WORDS if w in lower),
        "angry": sum(1 for w in _ANGRY_WORDS if w in lower),
        "surprised": sum(1 for w in _SURPRISED_WORDS if w in lower),
    }

    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return best
    return "neutral"


class EmotionStep(Step):
    """Analyze reply text and update character emotion state.

    Priority order:
      1. LLM-provided segments (ctx.segments with tones)
      2. Already-set ctx.emotion (from DecisionStep segment extraction)
      3. Keyword-based fallback detection
    """

    async def run(self, ctx: Context) -> None:
        # If LLM already provided structured segments with emotion, use those
        if ctx.segments:
            # Emotion already set by DecisionStep from segment tones
            self._update_character_emotion(ctx, ctx.emotion)
            return

        # If emotion was explicitly set upstream (not default 'neutral'), use it
        if ctx.emotion != "neutral":
            self._update_character_emotion(ctx, ctx.emotion)
            return

        text = ctx.reply_text or ctx.user_text or ""
        if not text:
            return

        # Fallback: keyword-based detection
        emotion = _detect_emotion(text)
        self._update_character_emotion(ctx, emotion)

    @staticmethod
    def _update_character_emotion(ctx: Context, emotion: str) -> None:
        """Update character EmotionState and context emotion fields."""
        character = ctx.state.get("character")
        if character is not None:
            try:
                character.emotion.set(emotion)
            except Exception:
                pass
            ctx.emotion = character.emotion.current
        else:
            ctx.emotion = emotion

        # Set intensity based on emotional weight
        if emotion != "neutral":
            ctx.emotion_intensity = min(1.0, ctx.emotion_intensity + 0.1)
        else:
            ctx.emotion_intensity = max(0.3, ctx.emotion_intensity - 0.05)
