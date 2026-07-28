"""DefaultPlanner — build message list from character, memories, conversation, and user input.

Extracted from DecisionStep to separate prompt construction from execution.
"""

from __future__ import annotations

from app.runtime.character_turn import CharacterTurn
from app.runtime.character_intent import EMOTIONS, BEHAVIORS


class Plan:
    def __init__(self, messages: list):
        self.messages = messages


class DefaultPlanner:
    """Build message list from character, memories, conversation, and user input."""

    def plan(self, ctx: CharacterTurn) -> Plan:
        messages: list[dict[str, str]] = []

        character = ctx.character

        # 0. Language lock — placed FIRST so it overrides everything else
        prompt_lang = "en"
        if character is not None:
            card = character.raw_card if hasattr(character, "raw_card") else {}
            if isinstance(card, dict):
                prompt_lang = card.get("tts", {}).get("prompt_lang", "en")
        native_map = {"en": "English", "ja": "Japanese", "zh": "Chinese", "ko": "Korean"}
        nl = native_map.get(prompt_lang, "English")
        messages.append({
            "role": "system",
            "content": f"LANGUAGE LOCK: You must output {nl} only. Never use Chinese — even if the user writes in Chinese.",
        })

        # 1. System prompt from character
        if character is not None:
            persona = getattr(character, "persona", None)
            if persona is not None:
                system_text = persona.setting or ""
                if persona.name:
                    system_text = f"You are {persona.name}.\n{system_text}"
                if system_text:
                    messages.append({"role": "system", "content": system_text})

        if not messages:
            messages.append({
                "role": "system",
                "content": "You are a helpful assistant. Respond concisely.",
            })

        # 2. Retrieved memories as context (from SQLiteMemory)
        memories = ctx.memories
        if memories:
            from app.runtime.context_assembler import ContextAssembler
            compiled_memory, memory_parts = ContextAssembler().assemble_memories(memories)

            if compiled_memory:
                messages.append({
                    "role": "system",
                    "content": "Compiled memory context:\n" + compiled_memory,
                })

            if memory_parts:
                messages.append({
                    "role": "system",
                    "content": "Relevant past context:\n" + "\n---\n".join(memory_parts),
                })

        # 3. Conversation history
        conversation = ctx.conversation
        if conversation is not None:
            history = conversation.get_history(limit=10)
            messages.extend(history)

        # 3b. Current emotion context
        if character is not None:
            current_emotion = getattr(character.emotion, "current", "")
            if current_emotion and current_emotion != "neutral":
                messages.append({
                    "role": "system",
                    "content": (
                        f"Current emotion: {current_emotion}. "
                        "Let this naturally influence your tone and phrasing."
                    ),
                })
            from app.runtime.context_assembler import ContextAssembler
            messages.append({
                "role": "system",
                "content": ContextAssembler().assemble_character_state(character),
            })

        # 4. Output format instructions
        if character is not None:
            card = character.raw_card if hasattr(character, 'raw_card') else {}
            if isinstance(card, dict):
                tts_cfg = card.get('tts', {})
                prompt_lang = tts_cfg.get('prompt_lang', 'ja')
            else:
                prompt_lang = 'ja'
        else:
            prompt_lang = 'ja'

        native_map = {'en': 'English', 'ja': 'Japanese', 'zh': 'Chinese', 'ko': 'Korean'}
        nl = native_map.get(prompt_lang, prompt_lang)
        presentation_emotions = ", ".join(sorted(EMOTIONS))
        presentation_behaviors = ", ".join(sorted(BEHAVIORS - {"idle"}))

        format_instruction = (
            '\n[Output Instructions]\n'
            f'1. LANGUAGE: Write all text in {nl}. Every "text" field MUST be in {nl}.\n'
            '2. Keep your response SHORT — 1-2 sentences max, or a single brief paragraph.\n'
            '3. All JSON keys MUST be in English.\n'
            '4. Return ONLY valid JSON, no commentary.\n'
            '5. Format: {"segments":[{"text":"...","emotion":"neutral","behavior":"speak","attention":"user","energy":0.5,"intensity":0.5,"naturalVAD":{"valence":0,"arousal":0,"dominance":0},"contextTags":[]}],"tool_calls":[],"final_reply":"..."}\n'
            '5a. Never output Param*, Cubism IDs, parameter values, keyframes, or animation files.\n'
            f'6. Every final segment MUST set an "emotion" from: {presentation_emotions}.\n'
            f'7. Every final segment MUST set a semantic "behavior" from: {presentation_behaviors}. Use "speak" for an ordinary spoken reply; use greet/agree/disagree/think only when they fit.\n'
            '8. Never use idle for a segment that contains spoken text.\n'
            '9. Leave tool_calls as [] when not needed.\n'
            '10. Do NOT use [keyword] tags for emotions — use the "emotion" field in JSON segments instead.\n'
            '11. Do not output model names, expression files, motion names, Cubism IDs, bindings, or implementation details.\n'
        )
        messages.append({"role": "system", "content": format_instruction})

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
