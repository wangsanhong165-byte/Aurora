"""TTSStep — synthesize speech from reply text.

Gracefully handles unavailable TTS service — logs and continues
without crashing the pipeline.
"""

import logging
from pathlib import Path

from app.runtime.pipeline import Step
from app.runtime.character_turn import CharacterTurn
from app.interfaces.tts import TTSInterface

logger = logging.getLogger("tts_step")
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _character_asset(character_id: str, value: object) -> str:
    """Resolve a character-card asset without allowing it to escape its pack."""
    relative = str(value or "").strip()
    if not relative:
        return ""
    character_dir = (_PROJECT_ROOT / "config" / "characters" / character_id).resolve()
    target = (character_dir / relative).resolve()
    try:
        target.relative_to(character_dir)
    except ValueError:
        return ""
    return str(target)


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

    engine = tts_cfg.get("engine", "")
    if engine:
        kwargs["engine"] = engine

    voice = tts_cfg.get("voice", "")
    if voice:
        kwargs["voice"] = voice

    reply_language = card.get("reply_language") or tts_cfg.get("text_lang")
    if reply_language:
        kwargs["text_lang"] = reply_language

    prompt_language = tts_cfg.get("prompt_lang", "")
    if prompt_language:
        kwargs["prompt_lang"] = prompt_language

    prompt_text = tts_cfg.get("prompt_text", "")
    if prompt_text:
        kwargs["prompt_text"] = prompt_text

    ref_audio = tts_cfg.get("ref_audio", {})
    if isinstance(ref_audio, dict):
        emotion = ctx.emotion or "neutral"
        ref_path = ref_audio.get(emotion) or ref_audio.get("neutral")
        if ref_path:
            resolved = _character_asset(str(getattr(character, "id", "")), ref_path)
            if resolved:
                kwargs["ref_audio_path"] = resolved

    custom_model = tts_cfg.get("custom_model", {})
    if isinstance(custom_model, dict):
        t2s = _character_asset(
            str(getattr(character, "id", "")), custom_model.get("t2s")
        )
        vits = _character_asset(
            str(getattr(character, "id", "")), custom_model.get("vits")
        )
        if t2s:
            kwargs["gpt_weights"] = t2s
        if vits:
            kwargs["sovits_weights"] = vits

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
