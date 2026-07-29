"""TTSStep — synthesize speech from reply text.

Gracefully handles unavailable TTS service — logs and continues
without crashing the pipeline.
"""

import logging

from app.runtime.pipeline import Step
from app.runtime.character_turn import CharacterTurn
from app.interfaces.tts import TTSInterface

logger = logging.getLogger("tts_step")


def _extract_voice_kwargs(ctx: CharacterTurn) -> dict:
    """Extract TTS voice parameters from the character card."""
    character = ctx.character
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

    async def run(self, ctx: CharacterTurn) -> None:
        if not ctx.reply_text:
            return
        voice_kwargs = _extract_voice_kwargs(ctx)
        try:
            audio = await self.tts.synthesize(ctx.reply_text, **voice_kwargs)
            if audio:
                ctx.audio = audio
        except Exception as exc:
            logger.warning("TTS unavailable (%s), continuing without audio", exc)
            ctx.audio = b""
            ctx.warnings.append(f"tts.failed:{exc}")
