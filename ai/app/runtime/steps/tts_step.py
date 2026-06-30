from app.runtime.pipeline import Step
from app.runtime.context import Context
from app.interfaces.tts import TTSInterface


def _extract_voice_kwargs(ctx: Context) -> dict:
    """Extract TTS voice parameters from the character card."""
    character = ctx.state.get("character")
    if character is None:
        return {}

    card = character.raw_card if hasattr(character, "raw_card") else {}
    if not isinstance(card, dict):
        return {}

    tts_cfg = card.get("tts", {})
    kwargs: dict = {}

    voice = tts_cfg.get("voice", "")
    if voice:
        kwargs["voice"] = voice

    lang = tts_cfg.get("prompt_lang", "")
    if lang:
        kwargs["language"] = lang

    ref_audio = tts_cfg.get("ref_audio", {})
    if isinstance(ref_audio, dict):
        emotion = ctx.emotion or "neutral"
        ref_path = ref_audio.get(emotion) or ref_audio.get("neutral")
        if ref_path:
            kwargs["ref_audio"] = ref_path

    return kwargs


class TTSStep(Step):
    """Synthesize speech from the reply text with character voice config."""

    def __init__(self, tts_provider: TTSInterface):
        self.tts = tts_provider

    async def run(self, ctx: Context) -> None:
        if not ctx.reply_text:
            return
        voice_kwargs = _extract_voice_kwargs(ctx)
        audio = await self.tts.synthesize(ctx.reply_text, **voice_kwargs)
        if audio:
            ctx.audio = audio
