"""CharacterPackLoader ? import .char ZIP files into characters/<id>/."""
from __future__ import annotations

import json
import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

import yaml


class CharacterPackLoader:
    """Parses .char ZIP files and imports them into the characters/ directory.

    Supported formats:
    - .char ZIP with character.yaml (???? style)
    - Plain character.json (our native format)
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base = base_dir or Path(__file__).resolve().parents[2]
        self._chars_dir = self._base / "config" / "characters"

    # ---- import from .char ZIP ------------------------------------------
    def import_char(self, zip_path: str | Path) -> str:
        """Import a .char ZIP file. Returns the character id."""
        zip_path = Path(zip_path)
        if not zip_path.exists():
            raise FileNotFoundError(str(zip_path))

        with zipfile.ZipFile(zip_path, "r") as zf:
            # Find character.yaml
            yaml_name = None
            for name in zf.namelist():
                if name.endswith("character.yaml") or name.endswith("character.yml"):
                    yaml_name = name
                    break

            if not yaml_name:
                raise ValueError("No character.yaml found in ZIP")

            # Parse character.yaml
            raw = yaml.safe_load(zf.read(yaml_name))
            if isinstance(raw, list):
                raw = raw[0]  # Some packs wrap in a list

            char_id = self._sanitize_id(raw.get("name", "unknown"))
            char_dir = self._chars_dir / char_id
            char_dir.mkdir(parents=True, exist_ok=True)

            # ---- convert to our schema ----
            card = self._convert_to_card(raw, char_id)

            # Write character.json
            card_path = char_dir / "character.json"
            with open(card_path, "w", encoding="utf-8") as f:
                json.dump(card, f, ensure_ascii=False, indent=2)

            # Extract sprites
            sprite_dir = char_dir / "portrait"
            sprite_dir.mkdir(exist_ok=True)
            self._extract_sprites(zf, raw, sprite_dir)

            # Extract models (TTS weights)
            model_dir = char_dir / "model"
            model_dir.mkdir(exist_ok=True)
            self._extract_models(zf, model_dir)

            # Extract voice references
            voice_dir = char_dir / "voice"
            voice_dir.mkdir(exist_ok=True)
            self._extract_voice(zf, voice_dir)

            # Update index.yaml
            self._update_index(char_id, card["name"])

        print(f"[PackLoader] Imported {char_id} -> {char_dir}")

        # Sync TTS models to GSVI
        self._sync_gsvi_models(char_id, char_dir, card)
        return char_id

    # ---- convert character.yaml -> our character.json --------------------
    def _convert_to_card(self, raw: dict, char_id: str) -> dict[str, Any]:
        """Convert raw character.yaml dict to our character.json schema."""
        name_raw = raw.get("name", char_id)
        name_dict: dict[str, str] = {}
        if isinstance(name_raw, dict):
            name_dict = name_raw
        else:
            name_dict = {"zh": str(name_raw), "ja": str(name_raw)}

        # Parse emotion_tags -> sprite tone mapping
        sprites: dict[str, dict] = {}
        emotion_text = raw.get("emotion_tags", "")
        raw_sprites = raw.get("sprites", [])
        if emotion_text and raw_sprites:
            sprites = self._parse_emotion_tags(emotion_text, raw_sprites)

        # Build TTS config
        prompt_text = raw.get("prompt_text", "")
        prompt_lang = raw.get("prompt_lang", "ja")

        tts_config: dict[str, Any] = {
            "engine": "gsvi-v2pro",
            "voice": name_dict.get("zh", str(name_raw)),
            "prompt_text": prompt_text,
            "prompt_lang": prompt_lang,
            "ref_audio": {"neutral": "voice/ref.wav"},
            "custom_model": {
                "t2s": "",   # will be filled by _extract_models
                "vits": "",
            },
        }

        # Use direct YAML fields for model paths
        gpt = raw.get("gpt_model_path", "") or ""
        sovits = raw.get("sovits_model_path", "") or ""
        refer = raw.get("refer_audio_path", "") or ""
        if gpt: tts_config["custom_model"]["t2s"] = "model/" + Path(gpt).name
        if sovits: tts_config["custom_model"]["vits"] = "model/" + Path(sovits).name
        if refer: tts_config["ref_audio"]["neutral"] = "voice/" + Path(refer).name
        # Build rules
        rules = {
            "tone_words": list(sprites.keys()) if sprites else ["neutral"],
            "max_segments_per_reply": 5,
            "avoid": ["避免不必要的动作描述", "避免角色崩坏", "Markdown"],
        }

        return {
            "$schema": "character/v2",
            "id": char_id,
            "name": name_dict,
            "color": raw.get("color", "#888888"),
            "sprite_prefix": raw.get("sprite_prefix", char_id),
            "character_setting": str(raw.get("character_setting", "")),
            "sprites": sprites,
            "tts": tts_config,
            "rules": rules,
        }

    # ---- parse emotion tags text -> sprite mapping ----------------------
    @staticmethod
    def _parse_emotion_tags(
        text: str, sprites: list[dict]
    ) -> dict[str, dict]:
        tone_map = {
            "平静": "neutral",
            "害羞": "shy",
            "开心": "happy",
            "吃醋": "jealous",
            "看着你": "looking",
            "害羞的说": "shy_talk",
            "震惊": "surprised",
            "生气": "angry",
            "担心": "worried",
            "严肃": "serious",
            "温柔": "gentle",
            "难过": "sad",
        }
        result: dict[str, dict] = {}
        lines = text.strip().split("\n")
        for i, line in enumerate(lines):
            if i >= len(sprites):
                break
            match = re.search(r"(\d+)\s*[?:：]\s*(.+)", line)
            if match:
                label = match.group(2).strip()
                tone = tone_map.get(label, "neutral")
                sprite = sprites[i]
                path = sprite.get("path", "")
                result[tone] = {"path": f"portrait/{path}", "label": label}
        if not result and sprites:
            result["neutral"] = {"path": f"portrait/{sprites[0].get('path', '')}", "label": "neutral"}
        return result

    # ---- extract helpers -------------------------------------------------
    def _extract_sprites(self, zf: zipfile.ZipFile, raw: dict, dest: Path) -> None:
        """Extract sprite PNGs from ZIP."""
        for item in raw.get("sprites", []):
            path = item.get("path", "")
            if path:
                try:
                    # Find the file in ZIP (may be in sprites/ subdir)
                    for name in zf.namelist():
                        if name.endswith(path):
                            zf.extract(name, dest.parent)
                            # Move from extract dir to dest
                            extracted = dest.parent / name
                            target = dest / Path(path).name
                            if extracted.exists() and extracted != target:
                                shutil.move(str(extracted), str(target))
                            break
                except Exception:
                    pass

    def _extract_models(self, zf: zipfile.ZipFile, dest: Path) -> None:
        """Extract TTS model weights (.ckpt, .pth) and reference audio."""
        for name in zf.namelist():
            if name.endswith((".ckpt", ".pth", ".wav")):
                basename = Path(name).name
                try:
                    with zf.open(name) as src:
                        with open(dest / basename, "wb") as dst:
                            dst.write(src.read())
                except Exception as exc:
                    print(f"[PackLoader] skip {name}: {exc}")

    def _extract_voice(self, zf: zipfile.ZipFile, dest: Path) -> None:
        """Extract reference audio to voice/."""
        for name in zf.namelist():
            if name.endswith(".wav") and "model" not in name.lower():
                basename = Path(name).name
                try:
                    with zf.open(name) as src:
                        with open(dest / basename, "wb") as dst:
                            dst.write(src.read())
                except Exception:
                    pass

    # ---- index management ------------------------------------------------
    def _update_index(self, char_id: str, name: dict) -> None:
        index_path = self._chars_dir / "index.yaml"
        index: dict[str, Any] = {"default": self._get_current_default(), "characters": []}

        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                existing = yaml.safe_load(f) or {}
            index["default"] = existing.get("default", index["default"])
            index["characters"] = existing.get("characters", [])

        # Avoid duplicates
        existing_ids = {c["id"] for c in index["characters"]}
        if char_id not in existing_ids:
            index["characters"].append({
                "id": char_id,
                "name": name.get("zh") or name.get("ja") or char_id,
                "path": f"characters/{char_id}/character.json",
            })

        with open(index_path, "w", encoding="utf-8") as f:
            yaml.dump(index, f, allow_unicode=True, default_flow_style=False)

    def _get_current_default(self) -> str:
        index_path = self._chars_dir / "index.yaml"
        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                existing = yaml.safe_load(f) or {}
            return existing.get("default", "amiya")
        return "amiya"

    # ---- auto-import .char files ----------------------------------------
    def _sync_gsvi_models(self, char_id: str, char_dir: Path, card: dict) -> None:
        """Copy character TTS model weights to GSVI v2Pro directories."""
        tts = card.get("tts", {})
        custom = tts.get("custom_model", {})
        t2s_src = custom.get("t2s", "")
        vits_src = custom.get("vits", "")
        ref_src = list(tts.get("ref_audio", {}).values())[0] if tts.get("ref_audio") else ""

        gsvi_dir = self._base / "models" / "tts" / "GPT-SoVITS-v2pro-20250604-nvidia50"
        gsvi_name = card.get("name", {}).get("zh") or char_id
        gpt_weights = gsvi_dir / "GPT_weights_v2Pro" / gsvi_name
        sovits_weights = gsvi_dir / "SoVITS_weights_v2Pro" / gsvi_name
        gpt_weights.mkdir(parents=True, exist_ok=True)
        sovits_weights.mkdir(parents=True, exist_ok=True)

        copied = 0
        # .ckpt -> GPT_weights_v2Pro (T2S model)
        if t2s_src:
            src = char_dir / t2s_src
            if src.exists():
                dst = gpt_weights / src.name
                if not dst.exists() or src.stat().st_size != dst.stat().st_size:
                    shutil.copy2(str(src), str(dst))
                    copied += 1
        # .pth -> SoVITS_weights_v2Pro (VITS model)
        if vits_src:
            src = char_dir / vits_src
            if src.exists():
                dst = sovits_weights / src.name
                if not dst.exists() or src.stat().st_size != dst.stat().st_size:
                    shutil.copy2(str(src), str(dst))
                    copied += 1
        # .wav reference audio -> GPT_weights_v2Pro
        for wav_file in char_dir.glob("**/*.wav"):
            dst = gpt_weights / wav_file.name
            if not dst.exists():
                shutil.copy2(str(wav_file), str(dst))
                copied += 1

        if copied:
            print(f"[PackLoader] GSVI models synced: {copied} file(s)")

    def auto_import(self) -> "list[str]":
        """Scan characters/*.char and auto-import any not yet extracted.
        Called by CharacterRegistry at startup. Returns list of new char ids."""
        imported: list[str] = []
        for char_file in sorted(self._chars_dir.glob("*.char")):
            stem = char_file.stem
            already = False
            for d in self._chars_dir.iterdir():
                if d.is_dir() and (d / "character.json").exists():
                    if d.name == stem or d.name == self._sanitize_id(stem):
                        already = True
                        break
            if already:
                continue
            try:
                char_id = self.import_char(str(char_file))
                imported.append(char_id)
                print(f"[PackLoader] auto-imported: {char_file.name} -> {char_id}")
            except Exception as exc:
                print(f"[PackLoader] auto-import FAILED for {char_file.name}: {exc}")
        return imported

    # ---- utility ---------------------------------------------------------
    @staticmethod
    def _sanitize_id(name: str) -> str:
        KNOWN = {}
        KNOWN[chr(0x6625)+chr(0x65E5)+chr(0x91CE)+chr(0x7A79)] = "sora"
        KNOWN[chr(0x30A2)+chr(0x30FC)+chr(0x30DF)+chr(0x30E4)] = "amiya"
        KNOWN[chr(0x963F)+chr(0x7C73)+chr(0x59E5)] = "amiya"
        if name in KNOWN:
            return KNOWN[name]
        safe = re.sub(r"[^\w\-]", "_", name).lower().strip("_")
        return safe or "unknown"

