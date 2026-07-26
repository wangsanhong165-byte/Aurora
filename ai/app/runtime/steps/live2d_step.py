from app.runtime.pipeline import Step
from app.runtime.character_turn import CharacterTurn
from app.runtime.character_intent import CharacterIntent


class Live2DStep(Step):
    """Update Live2D character expression and play audio.

    Populates ctx.live2d_intent with AI emotion/gesture decisions.
    The actual delivery is handled by RuntimeEventHandler._character_update(),
    which routes through the AvatarController permission system:
      - AI requests (priority=50) are submitted as AvatarRequest objects
      - PermissionManager arbitrates if USER (priority=100) has taken control
      - Denied AI requests are logged but don't block the pipeline

    Only pushes expression changes to avoid flickering from redundant
    set_expression calls on every pipeline run.
    """

    async def run(self, ctx: CharacterTurn) -> None:
        segment = None
        if ctx.segments:
            last = ctx.segments[-1]
            if isinstance(last, dict):
                segment = last

        if isinstance(segment, dict) and not segment.get("tone") and not segment.get("emotion"):
            segment = {**segment, "tone": ctx.emotion or "neutral"}

        # The runtime owns intent, not delivery. The V2 transport maps this
        # to a model-specific expression and sends it to the frontend.
        intent = CharacterIntent.from_llm_segment(segment or {"tone": ctx.emotion or "neutral"}, ctx.emotion_intensity)
        # Spoken output must retain a semantic presentation behavior even when
        # an older LLM response omits it or emits its former `idle` default.
        if ctx.reply_text and (not intent.behavior or intent.behavior == "idle"):
            intent = CharacterIntent(
                emotion=intent.emotion,
                behavior="speak",
                intensity=intent.intensity,
                attention=intent.attention,
                energy=intent.energy,
                duration_ms=intent.duration_ms,
                natural_vad=intent.natural_vad,
                context_tags=intent.context_tags,
            )
        ctx.live2d_intent = {**intent.to_dict(), "gesture": intent.behavior, "speaking": bool(ctx.audio)}
