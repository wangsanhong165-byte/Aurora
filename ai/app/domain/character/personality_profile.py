"""Stable, structured character personality kept separate from learned user state."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


_LIST_LIMIT = 12
_ITEM_LIMIT = 240
_RELATIONSHIP_LIMIT = 600
_TOTAL_LIMIT = 6_000


def _items(value: Any, field: str) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError(f"personality_profile.{field} must be an array")
    result: list[str] = []
    seen: set[str] = set()
    for raw in value:
        item = " ".join(str(raw or "").split())[:_ITEM_LIMIT]
        key = item.casefold()
        if not item or key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= _LIST_LIMIT:
            break
    return result


def _object(value: Any, field: str) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"personality_profile.{field} must be an object")
    return value


def normalize_personality_profile(value: Any) -> dict[str, Any]:
    """Validate and normalize the optional character-owned personality profile."""
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ValueError("personality_profile must be an object")

    speech = _object(value.get("speech_style"), "speech_style")
    preferences = _object(value.get("self_preferences"), "self_preferences")
    relationship = _object(value.get("relationship_style"), "relationship_style")
    normalized = {
        "values": _items(value.get("values"), "values"),
        "motivations": _items(value.get("motivations"), "motivations"),
        "speech_style": {
            "tone": _items(speech.get("tone"), "speech_style.tone"),
            "habits": _items(speech.get("habits"), "speech_style.habits"),
            "avoid": _items(speech.get("avoid"), "speech_style.avoid"),
        },
        "self_preferences": {
            "likes": _items(preferences.get("likes"), "self_preferences.likes"),
            "dislikes": _items(preferences.get("dislikes"), "self_preferences.dislikes"),
        },
        "relationship_style": {
            key: " ".join(str(relationship.get(key, "")).split())[:_RELATIONSHIP_LIMIT]
            for key in ("new", "familiar", "close")
        },
        "boundaries": _items(value.get("boundaries"), "boundaries"),
    }
    if len(str(normalized)) > _TOTAL_LIMIT:
        raise ValueError("personality_profile exceeds the supported size")
    if not any((
        normalized["values"],
        normalized["motivations"],
        any(normalized["speech_style"].values()),
        any(normalized["self_preferences"].values()),
        any(normalized["relationship_style"].values()),
        normalized["boundaries"],
    )):
        return {}
    return normalized


@dataclass(frozen=True)
class PersonalityProfile:
    """A stable role-owned profile; learned facts about the user never enter here."""

    data: dict[str, Any]

    @classmethod
    def from_value(cls, value: Any) -> "PersonalityProfile":
        return cls(normalize_personality_profile(value))

    @classmethod
    def from_card(cls, card: dict[str, Any]) -> "PersonalityProfile":
        try:
            return cls.from_value(card.get("personality_profile"))
        except ValueError:
            # Older imported packs are read defensively; the catalog remains the
            # strict write boundary for all newly saved cards.
            return cls({})

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self.data)

    def to_prompt(self) -> str:
        if not self.data:
            return ""
        lines = ["[结构化稳定人格]"]

        def append(label: str, values: list[str]) -> None:
            if values:
                lines.append(f"- {label}：" + "；".join(values))

        append("价值观", self.data["values"])
        append("长期动机", self.data["motivations"])
        speech = self.data["speech_style"]
        append("语言气质", speech["tone"])
        append("语言习惯", speech["habits"])
        append("表达时避免", speech["avoid"])
        preferences = self.data["self_preferences"]
        append("角色自己的喜好", preferences["likes"])
        append("角色自己的反感", preferences["dislikes"])
        relationship = self.data["relationship_style"]
        for key, label in (("new", "新关系"), ("familiar", "熟悉关系"), ("close", "亲密关系")):
            if relationship[key]:
                lines.append(f"- {label}：{relationship[key]}")
        append("行为边界", self.data["boundaries"])
        lines.append("- 这些是角色的稳定倾向；不要混入从交互学习到的用户状态，也不要逐条复述。")
        return "\n".join(lines)
