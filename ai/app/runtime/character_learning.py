"""Conservative, evidence-based character and memory learning."""

from __future__ import annotations

import re


# Single-character pronouns the regex cannot distinguish from real topics
# (e.g. "我喜欢你" -> topic="你" would store a bogus "用户喜欢你" preference).
_IGNORED_PREFERENCE_TOPICS = frozenset({
    "你", "您", "他", "她", "它", "我", "我们", "你们",
    "他们", "她们", "它们", "别人", "自己",
})

_PREFERENCE_PATTERNS = (
    (re.compile(r"我(?:很|最)?喜欢([\w\u3400-\u9fff]{1,24})"), 0.8),
    (re.compile(r"我(?:很|最)?不喜欢([\w\u3400-\u9fff]{1,24})"), -0.8),
)


def learn_from_turn(character, user_text: str, store, character_self=None) -> list[dict]:
    learned: list[dict] = []
    text = str(user_text or "").strip()
    if not text or character is None:
        return learned

    # Interaction itself moves affinity only slightly; explicit warmth adds more.
    delta = 0.002
    if any(word in text for word in ("谢谢", "喜欢你", "爱你", "辛苦了")):
        delta = 0.01
    elif any(word in text for word in ("讨厌你", "别烦我")):
        delta = -0.01
    if character_self is not None:
        character_self.adjust_affinity(delta)
    else:
        character.relationship.update_affinity(delta)

    for pattern, valence in _PREFERENCE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        topic = match.group(1).strip("，。！？,.!? ")
        if not topic or topic in _IGNORED_PREFERENCE_TOPICS:
            continue
        if character_self is not None:
            character_self.set_explicit_preference(topic, valence)
        else:
            character.preferences.set_explicit(topic, valence)
        content = f"用户{'喜欢' if valence > 0 else '不喜欢'}{topic}"
        memory_id = store.upsert_memory(
            memory_type="preference", subject="user",
            predicate="likes" if valence > 0 else "dislikes",
            content=content, character_id=character.id,
            importance=0.8, confidence=0.85,
            stable_key=f"preference:user:{topic}",
        )
        learned.append({"id": memory_id, "type": "preference", "content": content})

    if any(marker in text for marker in ("以后提醒我", "下次提醒我", "别忘了")):
        content = text[:160]
        store.upsert_memory(
            memory_type="open_loop", subject="user", predicate="follow_up",
            content=content, character_id=character.id,
            importance=0.85, confidence=0.8,
            stable_key=f"open_loop:{content}",
        )
        if character_self is not None:
            character_self.ensure_goal(content, priority=4)
        elif not any(goal.description == content for goal in character.goals.active):
            character.goals.add(content, priority=4)
        learned.append({"type": "open_loop", "content": content})

    return learned
