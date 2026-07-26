"""Bounded, deduplicated memory context for the LLM."""

from __future__ import annotations


class ContextAssembler:
    def assemble_character_state(self, character) -> str:
        relationship = character.relationship.to_dict()
        affinity = relationship.get("affinity", {}).get("default", 0.5)
        goals = [g.description for g in character.goals.top(3)]
        liked = [p.topic for p in character.preferences.top_liked(5)]
        disliked = [p.topic for p in character.preferences.top_disliked(3)
                     if p.valence < 0]
        lines = [
            "[Dynamic character state]",
            f"- mood: {character.mood.current}",
            f"- relationship affinity: {affinity:.2f}",
        ]
        if goals:
            lines.append("- active goals: " + "; ".join(goals))
        if liked:
            lines.append("- learned likes: " + "; ".join(liked))
        if disliked:
            lines.append("- learned dislikes: " + "; ".join(disliked))
        lines.append(
            "- Use this state subtly. Never recite scores or call it system state."
        )
        return "\n".join(lines)

    def assemble_memories(
        self, memories: list[dict], *, total_chars: int = 6000
    ) -> tuple[str, list[str]]:
        compiled = ""
        relevant: list[str] = []
        seen: set[str] = set()
        used = 0
        ordered = sorted(
            enumerate(memories),
            key=lambda pair: (
                pair[1].get("type") == "compiled",
                pair[1].get("source") == "hybrid",
                float(pair[1].get("data", {}).get("score", 0) or 0),
                pair[1].get("type") == "fact",
                pair[0],
            ),
            reverse=True,
        )
        for _, memory in ordered:
            if not isinstance(memory, dict):
                continue
            kind = memory.get("type", "")
            data = memory.get("data", {})
            if kind == "compiled":
                text = str(data.get("content", ""))[:3000]
                if text and not compiled:
                    compiled = text
                    used += len(text)
                continue
            if kind == "fact":
                fact = " ".join(str(data.get("fact", "")).split())
                text = f"[Fact] {fact}".strip()
            elif kind == "log":
                role = data.get("role", "")
                label = "User" if role == "user" else "Assistant"
                text = f"{label}: {str(data.get('content', ''))[:300]}"
            elif data.get("content"):
                label = {
                    "preference": "Preference",
                    "recent_state": "Recent state",
                    "episode": "Shared experience",
                    "relationship": "Relationship memory",
                    "open_loop": "Unfinished topic",
                    "fact": "Fact",
                }.get(kind, "Memory")
                text = f"[{label}] {str(data.get('content', ''))[:500]}"
            else:
                user, assistant = data.get("user", ""), data.get("assistant", "")
                text = f"User said: {user}\nYou said: {assistant}" if user and assistant else ""
            key = " ".join(text.lower().split())
            if not text or key in seen or used + len(text) > total_chars:
                continue
            seen.add(key)
            relevant.append(text)
            used += len(text)
        return compiled, relevant
