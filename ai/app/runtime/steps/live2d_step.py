from app.runtime.pipeline import Step
from app.runtime.context import Context
from app.interfaces.live2d import Live2DInterface


class Live2DStep(Step):
    """Update Live2D character expression and play audio."""

    def __init__(self, live2d_provider: Live2DInterface):
        self.live2d = live2d_provider

    async def run(self, ctx: Context) -> None:
        emotion = ctx.emotion or "neutral"
        await self.live2d.set_expression(emotion)

        # Extract gesture from the last segment's gesture field
        if ctx.segments:
            gesture = ctx.segments[-1].get("gesture", "")
            if gesture and gesture != "none":
                await self.live2d.set_gesture(gesture)

        if ctx.audio:
            await self.live2d.speak(ctx.audio, emotion)
