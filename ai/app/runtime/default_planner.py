"""DefaultPlanner — build message list from character, memories, conversation, and user input.

Extracted from DecisionStep to separate prompt construction from execution.
"""

from __future__ import annotations

from pathlib import Path

from app.runtime.character_turn import CharacterTurn
from app.runtime.character_intent import EMOTIONS, BEHAVIORS
from app.runtime.prompt_config import PromptConfigStore
from app.runtime.prompt_overrides import PromptOverrideStore
from app.runtime.presentation_capabilities import (
    Live2DPresentationRegistry,
    get_presentation_registry,
)


class Plan:
    def __init__(self, messages: list, sources: list[str] | None = None):
        self.messages = messages
        self.sources = list(sources or [])


def _reply_language(card: object) -> str:
    if not isinstance(card, dict):
        return "en"
    tts = card.get("tts", {})
    if not isinstance(tts, dict):
        tts = {}
    return str(card.get("reply_language") or tts.get("prompt_lang") or "en")


class DefaultPlanner:
    """Build message list from character, memories, conversation, and user input."""

    def __init__(
        self,
        prompt_store: PromptOverrideStore | None = None,
        prompt_config_store: PromptConfigStore | None = None,
        presentation_registry: Live2DPresentationRegistry | None = None,
    ):
        prompt_dir = Path(__file__).resolve().parents[2] / "data" / "prompts"
        self._prompt_store = prompt_store or PromptOverrideStore(
            prompt_dir
        )
        self._prompt_config_store = prompt_config_store or PromptConfigStore(prompt_dir)
        self._presentation_registry = presentation_registry or get_presentation_registry()

    def plan(self, ctx: CharacterTurn) -> Plan:
        presentation = getattr(ctx, "presentation", None)
        if presentation is None:
            presentation = self._presentation_registry.snapshot()
            ctx.presentation = presentation
        messages: list[dict[str, str]] = []
        sources: list[str] = []

        character = ctx.character
        character_id = str(getattr(character, "id", "")) if character is not None else ""

        def append_system(source_id: str, default_content: str) -> None:
            content: str | None = default_content
            if character_id:
                try:
                    content = self._prompt_config_store.resolve(
                        character_id,
                        source_id,
                        default_content,
                    )
                except ValueError:
                    content = default_content
            if content and content.strip():
                messages.append({"role": "system", "content": content.strip()})
                sources.append(source_id)

        # 0. Language lock — placed FIRST so it overrides everything else
        prompt_lang = "en"
        if character is not None:
            card = character.raw_card if hasattr(character, "raw_card") else {}
            if isinstance(card, dict):
                prompt_lang = _reply_language(card)
        native_map = {"en": "English", "ja": "Japanese", "zh": "Chinese", "ko": "Korean", "yue": "Cantonese Chinese"}
        native_override = {"en": "你只能用 English 输出", "ja": "日本語のみで出力してください", "zh": "请用中文输出", "ko": "한국어로만 출력하세요", "yue": "请只用粤语输出"}
        nl = native_map.get(prompt_lang, "English")
        append_system(
            "language",
            f"LANGUAGE LOCK: Your native language is {nl}. Even if the user writes to you in another language like Chinese, you MUST reply in {nl} ONLY. {native_override.get(prompt_lang, f'You must output {nl} only.')} The user will understand your {nl} reply even if they wrote in another language. This rule is NON-NEGOTIABLE — do not mirror the user's language.",
        )

        # 1. System prompt from character
        if character is not None:
            persona = getattr(character, "persona", None)
            if persona is not None:
                system_text = persona.setting or ""
                if persona.display_name:
                    system_text = f"You are {persona.display_name}.\n{system_text}"
                if system_text:
                    append_system("persona", system_text)

            try:
                prompt_override = self._prompt_store.get(character_id) if character_id else ""
            except ValueError:
                prompt_override = ""
            if prompt_override:
                messages.append({
                    "role": "system",
                    "content": (
                        "Additional project instructions for this character:\n"
                        + prompt_override
                    ),
                })
                sources.append("addition")

        if character is None and not messages:
            messages.append({
                "role": "system",
                "content": "You are a helpful assistant. Respond concisely.",
            })
            sources.append("system")

        # 2. Output format instructions — static per character. Kept BEFORE all
        # per-turn context (memory, state, history) so the prompt-cache prefix
        # stays byte-identical across turns; DeepSeek then serves the cached
        # segment instead of re-reading the format spec on every request.
        if character is not None:
            card = character.raw_card if hasattr(character, 'raw_card') else {}
            if isinstance(card, dict):
                prompt_lang = _reply_language(card)
            else:
                prompt_lang = 'en'
        else:
            prompt_lang = 'en'

        native_map = {'en': 'English', 'ja': 'Japanese', 'zh': 'Chinese', 'ko': 'Korean', 'yue': 'Cantonese Chinese'}
        nl = native_map.get(prompt_lang, prompt_lang)
        presentation_emotions = ", ".join(
            getattr(ctx, "allowed_emotions", presentation.allowed_emotions)
            or tuple(sorted(EMOTIONS))
        )
        presentation_behaviors = ", ".join(sorted(BEHAVIORS - {"idle"}))

        format_instruction = (
            '\n[Output Instructions]\n'
            f'1. LANGUAGE: every JSON field value — "text", "final_reply", etc. — MUST be written in {nl}, per the LANGUAGE LOCK above.\n'
            '2. Keep your response SHORT — 1-2 sentences max, or a single brief paragraph.\n'
            '3. All JSON keys MUST be in English.\n'
            '4. Return ONLY valid JSON, no commentary.\n'
            '5. Format: {"segments":[{"text":"...","emotion":"neutral","behavior":"speak","attention":"user","energy":0.5,"intensity":0.5,"naturalVAD":{"valence":0,"arousal":0,"dominance":0},"contextTags":[],"motionPlan":{"durationMs":1200,"steps":[{"atMs":0,"durationMs":600,"primitive":"nod","intensity":0.5}]}}],"tool_calls":[],"final_reply":"..."}\n'
            '5a. motionPlan is optional, but use 1-3 restrained semantic body-language beats when the segment contains emphasis, an emotional shift, greeting, agreement, disagreement, reflection, reassurance, or playful intent. Omit it only for genuinely short neutral speech; the runtime supplies a subtle deterministic fallback. Do not repeat the same primitive in adjacent segments. Allowed primitives: nod, tilt_left, tilt_right, lean_forward, lean_back, sway, look_left, look_right, breathe, shrug. durationMs must be 300-8000, step durationMs 120-2500, and intensity 0-1. The runtime rescales segment plans to the decoded speech duration, so atMs is relative to this segment and must not guess wall-clock playback time.\n'
            '5b. Never output Param*, Cubism IDs, parameter values, keyframes, animation files, or extra motionPlan fields.\n'
            f'6. Every final segment MUST set an "emotion" from: {presentation_emotions}.\n'
            '6a. Choose only from the listed emotions and judge THIS segment independently. Ordinary informative speech defaults to neutral. Use a conspicuous emotion only when the segment provides matching semantic evidence; if the ideal label is unavailable, choose the closest listed emotion or neutral. shy and embarrassed require explicit evidence of bashfulness, embarrassment, blushing, or romantic awkwardness when those labels are available. Never carry a previous emotion forward merely for continuity, and do not assign one conspicuous expression to every sentence.\n'
            f'7. Every final segment MUST set a semantic "behavior" from: {presentation_behaviors}. Describe the communicative act, not merely the fact that audio is playing: greetings use greet, agreement uses agree, disagreement uses disagree, reflection uses think, and only ordinary speech uses speak.\n'
            '8. Never use idle for a segment that contains spoken text.\n'
            '9. Leave tool_calls as [] when not needed.\n'
            '10. Do NOT use [keyword] tags for emotions — use the "emotion" field in JSON segments instead.\n'
            '11. Do not output model names, expression files, motion names, Cubism IDs, bindings, or implementation details.\n'
            '12. SPOKEN TEXT ONLY: ALWAYS produce a spoken reply. "final_reply" and every segment "text" must be non-empty natural language containing only words the character actually says aloud. Never narrate, announce, or claim visible actions in spoken text (for example, blinking, leaning closer, or making a face). Visible performance belongs only in "emotion", "behavior", "naturalVAD", and "motionPlan". If those fields cannot represent an action, do not claim that it happened. Never return empty, blank, or whitespace-only content — even for very short or unclear user input, respond naturally.\n'
        )
        append_system("output_protocol", format_instruction)

        # 3. Retrieved memories as context (from SQLiteMemory)
        memories = ctx.memories
        compiled_memory = ""
        memory_parts: list[str] = []
        if memories:
            from app.runtime.context_assembler import ContextAssembler
            compiled_memory, memory_parts = ContextAssembler().assemble_memories(memories)

        append_system(
            "memory_summary",
            "Compiled memory context:\n" + compiled_memory if compiled_memory else "",
        )
        append_system(
            "relevant_memory",
            "Relevant past context:\n" + "\n---\n".join(memory_parts) if memory_parts else "",
        )

        # 4. Conversation history
        conversation = ctx.conversation
        if conversation is not None:
            history = conversation.get_history(limit=10)
            messages.extend(history)
            sources.extend(
                "assistant_history" if item.get("role") == "assistant" else "user_history"
                for item in history
            )

        # 4b. Current emotion context
        if character is not None:
            current_emotion = getattr(character.emotion, "current", "")
            emotion_content = ""
            if current_emotion and current_emotion != "neutral":
                emotion_content = (
                        f"Previous expression state: {current_emotion}. "
                        "This is continuity context, not a default for the next segment. "
                        "Re-evaluate emotion from the current message and reply; do not reuse it by default."
                )
            append_system("emotion", emotion_content)
            from app.runtime.context_assembler import ContextAssembler
            append_system(
                "character_state",
                ContextAssembler().assemble_character_state(character, ctx.memories),
            )

        # 5. Current user input
        user_text = ctx.user_text or ctx.event.payload.get("text", "")
        if user_text and ctx.input_origin == "initiative":
            initiative = ctx.initiative
            messages.append({
                "role": "system",
                "content": (
                    "Trusted initiative event (not a user message):\n"
                    f"{user_text}\nStructured event: {initiative}"
                ),
            })
            sources.append("initiative")
        elif user_text:
            messages.append({"role": "user", "content": user_text})
            sources.append("user_input")

        return Plan(messages=messages, sources=sources)
