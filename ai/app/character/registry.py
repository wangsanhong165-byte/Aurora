"""CharacterRegistry  scan characters/*/character.json, load and validate character cards."""
import json
import os
from pathlib import Path
from typing import Any, Callable

import yaml


class CharacterRegistry:
    """Scans characters/ directory for character.json files and manages active character."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base = base_dir or Path(__file__).resolve().parents[2]
        self._chars_dir = self._base / "config" / "characters"
        self._index_path = self._chars_dir / "index.yaml"
        self._characters: dict[str, dict[str, Any]] = {}
        self._active_id: str = ""
        self._on_activate: list[Callable[[str, str], None]] = []  # (old_id, new_id)
        self._scan()

    # ---- scan -----------------------------------------------------------
    def _scan(self) -> None:
        from app.character.loader import CharacterPackLoader
        loader = CharacterPackLoader(self._base)
        loader.auto_import()

        if not self._chars_dir.exists():
            return
        for char_dir in sorted(self._chars_dir.iterdir()):
            if not char_dir.is_dir():
                continue
            card_path = char_dir / "character.json"
            if not card_path.exists():
                continue
            try:
                with open(card_path, "r", encoding="utf-8") as fh:
                    card = json.load(fh)
                self._validate(card)
                self._characters[card["id"]] = card
            except Exception as exc:
                print(f"[CharacterRegistry] skip {char_dir.name}: {exc}")

        if self._index_path.exists():
            with open(self._index_path, "r", encoding="utf-8") as fh:
                index = yaml.safe_load(fh) or {}
            default = index.get("default", "")
            if default in self._characters:
                self._active_id = default
        if not self._active_id and self._characters:
            self._active_id = next(iter(self._characters))

    # ---- validate -------------------------------------------------------
    @staticmethod
    def _validate(card: dict[str, Any]) -> None:
        required = ["id", "name"]
        for key in required:
            if key not in card:
                raise ValueError(f"missing required field: {key}")
        if "system_prompt" not in card and "character_setting" not in card:
            raise ValueError(f"missing system_prompt or character_setting in {card['id']}")
        rules = card.get("rules", {})
        emotions = rules.get("emotion_words", [])
        sprites = card.get("sprites", card.get("portraits", {}))
        for emotion in emotions:
            if emotion not in sprites:
                print(
                    "[CharacterRegistry] warn: sprite missing for emotion "
                    f"'{emotion}' in {card['id']}"
                )

    # ---- public API -----------------------------------------------------
    def list_ids(self) -> list[str]:
        return list(self._characters.keys())

    def get(self, char_id: str | None = None) -> dict[str, Any]:
        cid = char_id or self._active_id
        if cid not in self._characters:
            raise KeyError(f"Character not found: {cid}")
        return self._characters[cid]

    def activate(self, char_id: str) -> None:
        if char_id not in self._characters:
            raise KeyError(f"Character not found: {char_id}")
        old = self._active_id
        self._active_id = char_id
        if old and old != char_id:
            for cb in self._on_activate:
                try:
                    cb(old, char_id)
                except Exception as exc:
                    print(f"[CharacterRegistry] on_activate callback error: {exc}")

    def on_activate(self, callback: Callable[[str, str], None]) -> None:
        """Register callback(old_id, new_id) for persona switch handling."""
        self._on_activate.append(callback)

    @property
    def active(self) -> dict[str, Any]:
        return self.get(self._active_id)

    @property
    def active_id(self) -> str:
        return self._active_id

    @property
    def emotion_words(self) -> list[str]:
        return self.active.get("rules", {}).get(
            "emotion_words",
            ["neutral"],
        )

    def portrait_for(self, emotion: str) -> str | None:
        sprites = self.active.get("sprites", self.active.get("portraits", {}))
        match = sprites.get(emotion, sprites.get("neutral", {}))
        if isinstance(match, dict):
            return match.get("path")
        return match

    def tts_ref_for(self, emotion: str) -> str | None:
        refs = self.active.get("tts", {}).get("ref_audio", {})
        return refs.get(emotion) or refs.get("neutral")

    def __repr__(self) -> str:
        return f"CharacterRegistry(active={self._active_id!r}, chars={list(self._characters)!r})"
