"""DefaultPlanner — build message list from character, memories, conversation, and user input.

Extracted from DecisionStep to separate prompt construction from execution.
"""

from __future__ import annotations

from pathlib import Path

from app.runtime.character_turn import CharacterTurn
from app.runtime.character_intent import EMOTIONS, BEHAVIORS
from app.runtime.prompt_config import PromptConfigStore
from app.runtime.prompt_overrides import PromptOverrideStore


class Plan:
    def __init__(self, messages: list):
        self.messages = messages


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
    ):
        prompt_dir = Path(__file__).resolve().parents[2] / "data" / "prompts"
        self._prompt_store = prompt_store or PromptOverrideStore(
            prompt_dir
        )
        self._prompt_config_store = prompt_config_store or PromptConfigStore(prompt_dir)

    def plan(self, ctx: CharacterTurn) -> Plan:
        messages: list[dict[str, str]] = []

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
                if persona.name:
                    system_text = f"You are {persona.name}.\n{system_text}"
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

        if character is None and not messages:
            messages.append({
                "role": "system",
                "content": "You are a helpful assistant. Respond concisely.",
            })

        # 2. Retrieved memories as context (from SQLiteMemory)
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

        # 3. Conversation history
        conversation = ctx.conversation
        if conversation is not None:
            history = conversation.get_history(limit=10)
            messages.extend(history)

        # 3b. Current emotion context
        if character is not None:
            current_emotion = getattr(character.emotion, "current", "")
            emotion_content = ""
            if current_emotion and current_emotion != "neutral":
                emotion_content = (
                        f"Current emotion: {current_emotion}. "
                        "Let this naturally influence your tone and phrasing."
                )
            append_system("emotion", emotion_content)
            from app.runtime.context_assembler import ContextAssembler
            append_system(
                "character_state",
                ContextAssembler().assemble_character_state(character),
            )

        # 4. Output format instructions
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
        presentation_emotions = ", ".join(sorted(EMOTIONS))
        presentation_behaviors = ", ".join(sorted(BEHAVIORS - {"idle"}))

        format_instruction = (
            '\n[Output Instructions]\n'
            f'1. LANGUAGE: Write ALL text in {nl}. Every "text" field MUST be in {nl}. CRITICAL: The user may write in Chinese, but you MUST respond in {nl}. Never mirror the user language.\n'
            '2. Keep your response SHORT — 1-2 sentences max, or a single brief paragraph.\n'
            '3. All JSON keys MUST be in English.\n'
            '4. Return ONLY valid JSON, no commentary.\n'
            '5. Format: {"segments":[{"text":"...","emotion":"neutral","behavior":"speak","attention":"user","energy":0.5,"intensity":0.5,"naturalVAD":{"valence":0,"arousal":0,"dominance":0},"contextTags":[],"motionPlan":{"durationMs":1200,"steps":[{"atMs":0,"durationMs":600,"primitive":"nod","intensity":0.5}]}}],"tool_calls":[],"final_reply":"..."}\n'
            '5a. motionPlan is optional. Use it only when a visible gesture materially helps; ordinary speech should omit it. Use at most 3 steps. Allowed primitives: nod, tilt_left, tilt_right, lean_forward, lean_back, sway, look_left, look_right, breathe, shrug, arm_wave, tail_sway. Use arm_wave or tail_sway only for an intentional visible gesture. durationMs must be 300-8000, step durationMs 120-2500, and intensity 0-1.\n'
            '5b. Never output Param*, Cubism IDs, parameter values, keyframes, animation files, or extra motionPlan fields.\n'
            f'6. Every final segment MUST set an "emotion" from: {presentation_emotions}.\n'
            f'7. Every final segment MUST set a semantic "behavior" from: {presentation_behaviors}. Use "speak" for an ordinary spoken reply; use greet/agree/disagree/think only when they fit.\n'
            '8. Never use idle for a segment that contains spoken text.\n'
            '9. Leave tool_calls as [] when not needed.\n'
            '10. Do NOT use [keyword] tags for emotions — use the "emotion" field in JSON segments instead.\n'
            '11. Do not output model names, expression files, motion names, Cubism IDs, bindings, or implementation details.\n'
        )
        append_system("output_protocol", format_instruction)

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
        elif user_text:
            messages.append({"role": "user", "content": user_text})

        return Plan(messages=messages)
