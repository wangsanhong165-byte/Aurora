"""ReflectionStrategy — post-turn reflection and insight extraction.

After the LLM responds, this strategy optionally performs a secondary
LLM call to reflect on the interaction and extract insights for memory,
relationship updates, and preference learning.
"""

from typing import Any

from app.runtime.context import Context
from app.brain.base import PlanningStrategy, Plan


class ReflectionStrategy(PlanningStrategy):
    """Post-turn reflection strategy.

    In addition to the standard prompt, this strategy appends a reflection
    step that asks the LLM to analyze the interaction and extract:
      - Key facts about the user
      - Emotional impact on the character
      - Relationship affinity changes
      - Preference signals

    The reflection output is stored in ctx.state for downstream steps
    (MemorySaveStep, EmotionStep) to consume.

    Use by injecting into DecisionStep:
        step = DecisionStep(llm, tools, planner=ReflectionStrategy())
    """

    name: str = "reflection"

    def __init__(self, llm_provider: Any = None):
        super().__init__()
        self._llm = llm_provider

    def plan(self, ctx: Context) -> Plan:
        # First, build the standard prompt (same as PromptStrategy)
        messages: list[dict[str, str]] = []

        character = ctx.state.get("character")
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

        memories = ctx.state.get("memories", [])
        if memories:
            memory_parts = []
            compiled_memory = ""
            for m in memories[-10:]:
                mtype = m.get("type", "") if isinstance(m, dict) else ""
                data = m.get("data", {}) if isinstance(m, dict) else {}
                if mtype == "compiled":
                    compiled_memory = data.get("content", "")
                elif mtype == "fact":
                    fact = data.get("fact", "")
                    if fact:
                        memory_parts.append(f"[Fact] {fact}")
                elif mtype == "log":
                    content = data.get("content", "")
                    role = data.get("role", "")
                    if content and role:
                        label = "User" if role == "user" else "Assistant"
                        memory_parts.append(f"{label}: {content[:200]}")

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

        conversation = ctx.state.get("conversation")
        if conversation is not None:
            history = conversation.get_history(limit=10)
            messages.extend(history)

        tone_words = ["neutral"]
        prompt_lang = "ja"
        if character is not None:
            card = character.raw_card if hasattr(character, "raw_card") else {}
            if isinstance(card, dict):
                tts_cfg = card.get("tts", {})
                prompt_lang = tts_cfg.get("prompt_lang", "ja")
                tone_words = card.get("rules", {}).get("tone_words", ["neutral"])

        native_map = {"en": "English", "ja": "Japanese", "zh": "Chinese", "ko": "Korean"}
        nl = native_map.get(prompt_lang, prompt_lang)
        first_tone = tone_words[0] if tone_words else "neutral"

        format_instruction = (
            "\n[Output Instructions]\n"
            f"1. Speak naturally as yourself. Use {nl}.\n"
            f"2. Each segment has a 'text' field containing {nl} text.\n"
            "3. Return ONLY valid JSON, no commentary.\n"
            f"4. Format: {{\"segments\":[{{\"text\":\"...\",\"tone\":\"{first_tone}\",\"gesture\":\"none\"}}],\"tool_calls\":[],\"final_reply\":\"...\",\"_reflection\":{{\"facts\":[],\"affinity_delta\":0.0,\"preference_signals\":[]}}}}\n"
            f"5. tone controls facial expression. Valid tones: {', '.join(tone_words)}\n"
            '6. gesture values: "none"(default), "wave", "tilt", "nod", "shrug"\n'
            '7. Leave tool_calls as [] when not needed.\n'
            '8. "_reflection" is an internal field for memory/relationship updates. '
            'Set affinity_delta to -0.1 to 0.1 based on how the interaction felt. '
            'List facts learned about the user in "facts". '
            'List topics the user seems to like/dislike in "preference_signals".\n'
        )
        messages.append({"role": "system", "content": format_instruction})

        user_text = ctx.user_text or ctx.event.payload.get("text", "")
        if user_text:
            messages.append({"role": "user", "content": user_text})

        self._metadata["strategy"] = "reflection"
        self._metadata["has_llm"] = self._llm is not None
        return Plan(messages=messages)
