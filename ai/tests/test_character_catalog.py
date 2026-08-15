import asyncio
import json
import struct
import wave
import zipfile
import zlib
from pathlib import Path

import yaml
import pytest

from app.character.catalog import CharacterCatalog
from app.character.registry import CharacterRegistry
from app.character.voices import VoiceRegistry
from app.runtime.management import RuntimeManager
from app.transport.management import ManagementHandler
from app.memory.store import MemoryStore
from app.memory import compiler as compiler_mod


def _write_complete_asset_sources(tmp_path: Path) -> dict[str, str]:
    live2d = tmp_path / "source-live2d"
    live2d.mkdir()
    (live2d / "avatar.moc3").write_bytes(b"MOC3\x04" + b"\0" * 2048)
    def png_chunk(kind, data):
        return (
            struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )
    png = b"\x89PNG\r\n\x1a\n"
    png += png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    png += png_chunk(b"IDAT", zlib.compress(b"\x00\0\0\0"))
    png += png_chunk(b"IEND", b"")
    (live2d / "texture_00.png").write_bytes(png)
    (live2d / "avatar.model3.json").write_text(json.dumps({
        "Version": 3,
        "FileReferences": {
            "Moc": "avatar.moc3",
            "Textures": ["texture_00.png"],
        },
    }), encoding="utf-8")

    ref_audio = tmp_path / "reference.wav"
    t2s = tmp_path / "voice.ckpt"
    vits = tmp_path / "voice.pth"
    with wave.open(str(ref_audio), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16_000)
        output.writeframes(b"\0\0" * 320)
    for path in (t2s, vits):
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("model/data.pkl", b"checkpoint" * 128)
    vits_bytes = vits.read_bytes()
    vits.write_bytes(b"05" + vits_bytes[2:])
    return {
        "live2d_directory": str(live2d),
        "reference_audio": str(ref_audio),
        "t2s_model": str(t2s),
        "vits_model": str(vits),
    }


def test_user_can_import_a_complete_character_pack_through_one_interface(tmp_path):
    assets = _write_complete_asset_sources(tmp_path)
    catalog = CharacterCatalog(tmp_path)

    created = catalog.create({
        "id": "lantern",
        "name": "Lantern",
        "reply_language": "zh",
        "persona": "你是一位安静但好奇的数字伙伴。",
        "assets": assets,
        "voice": {
            "prompt_text": "这是用于克隆声线的参考文本。",
            "prompt_language": "zh",
        },
    })

    assert created == {
        "id": "lantern",
        "name": "Lantern",
        "reply_language": "zh",
        "live2d_model": "lantern",
        "voice_configured": True,
    }

    character_dir = tmp_path / "config" / "characters" / "lantern"
    card = json.loads((character_dir / "character.json").read_text("utf-8"))
    assert card["reply_language"] == "zh"
    assert card["live2d"]["model"] == "lantern"
    assert card["tts"]["prompt_lang"] == "zh"
    assert card["tts"]["ref_audio"]["neutral"] == "model/reference.wav"
    assert card["tts"]["custom_model"] == {
        "t2s": "model/voice.ckpt",
        "vits": "model/voice.pth",
    }

    model_dir = tmp_path / "models" / "live2d-models" / "lantern"
    assert (model_dir / "lantern.model3.json").is_file()
    assert (model_dir / "avatar.moc3").is_file()
    assert (character_dir / "model" / "reference.wav").is_file()
    assert (character_dir / "model" / "voice.ckpt").is_file()
    assert (character_dir / "model" / "voice.pth").is_file()

    live2d_config = json.loads(
        (tmp_path / "config" / "live2d_models.json").read_text("utf-8")
    )
    assert live2d_config["lantern"]["prompt_emotions"] == ["neutral"]

    index = yaml.safe_load(
        (tmp_path / "config" / "characters" / "index.yaml").read_text("utf-8")
    )
    assert index["characters"] == [{
        "id": "lantern",
        "name": "Lantern",
        "path": "characters/lantern/character.json",
    }]
    assert CharacterRegistry(tmp_path).list_ids() == ["lantern"]

    profile = json.loads(
        (tmp_path / "config" / "avatar_profiles" / "lantern.json").read_text("utf-8")
    )
    assert profile["model"] == "lantern"


def test_catalog_lists_imported_roles_from_disk_instead_of_a_frontend_constant(tmp_path):
    assets = _write_complete_asset_sources(tmp_path)
    catalog = CharacterCatalog(tmp_path)
    created = catalog.create({
        "id": "lantern",
        "name": "Lantern",
        "reply_language": "ja",
        "persona": "A concise persona.",
        "assets": assets,
        "voice": {"prompt_text": "参照音声です。", "prompt_language": "ja"},
    })

    assert catalog.list() == [created]


class _Runtime:
    def get_character_info(self):
        return {"card": {"id": "monika"}, "name": "Monika"}


def test_management_api_lists_and_creates_complete_character_packs(tmp_path):
    assets = _write_complete_asset_sources(tmp_path)
    manager = RuntimeManager(base_dir=tmp_path, runtime=_Runtime())
    handler = ManagementHandler()
    handler._manager = manager

    before = asyncio.run(handler.handle("get_character_catalog", {}, "catalog-1"))[0]
    created = asyncio.run(handler.handle("create_character", {
        "id": "lantern",
        "name": "Lantern",
        "reply_language": "zh",
        "persona": "A concise persona.",
        "assets": assets,
        "voice": {"prompt_text": "reference", "prompt_language": "en"},
    }, "catalog-2"))[0]
    after = asyncio.run(handler.handle("get_character_catalog", {}, "catalog-3"))[0]

    assert before.payload.data == {
        "active_character_id": "monika",
        "characters": [],
    }
    assert created.payload.data["character"]["id"] == "lantern"
    assert after.payload.data["characters"] == [created.payload.data["character"]]


def test_failed_registration_restores_indexes_and_removes_partial_assets(tmp_path, monkeypatch):
    assets = _write_complete_asset_sources(tmp_path)
    config_path = tmp_path / "config" / "live2d_models.json"
    index_path = tmp_path / "config" / "characters" / "index.yaml"
    config_path.parent.mkdir(parents=True)
    index_path.parent.mkdir(parents=True)
    config_path.write_text('{"existing": {}}\n', encoding="utf-8")
    index_path.write_text("default: existing\ncharacters: []\n", encoding="utf-8")
    original_config = config_path.read_bytes()
    original_index = index_path.read_bytes()
    catalog = CharacterCatalog(tmp_path)
    original_register = catalog._register

    def fail_after_registration(character_id, name):
        original_register(character_id, name)
        raise OSError("simulated registration failure")

    monkeypatch.setattr(catalog, "_register", fail_after_registration)
    with pytest.raises(OSError, match="simulated registration failure"):
        catalog.create({
            "id": "lantern", "name": "Lantern", "reply_language": "zh",
            "persona": "A concise persona.", "assets": assets,
            "voice": {"prompt_text": "reference", "prompt_language": "en"},
        })

    assert config_path.read_bytes() == original_config
    assert index_path.read_bytes() == original_index
    assert not (tmp_path / "config" / "characters" / "lantern").exists()
    assert not (tmp_path / "models" / "live2d-models" / "lantern").exists()
    assert not (tmp_path / "config" / "avatar_profiles" / "lantern.json").exists()


def test_import_rejects_live2d_when_any_declared_resource_is_missing(tmp_path):
    assets = _write_complete_asset_sources(tmp_path)
    model_path = Path(assets["live2d_directory"]) / "avatar.model3.json"
    model = json.loads(model_path.read_text("utf-8"))
    model["FileReferences"]["Expressions"] = [
        {"Name": "smile", "File": "expressions/smile.exp3.json"},
    ]
    model_path.write_text(json.dumps(model), encoding="utf-8")

    with pytest.raises(ValueError, match="smile.exp3.json"):
        CharacterCatalog(tmp_path).create({
            "id": "lantern", "name": "Lantern", "reply_language": "zh",
            "persona": "A concise persona.", "assets": assets,
            "voice": {"prompt_text": "reference", "prompt_language": "en"},
        })


def test_import_copies_only_resources_declared_by_the_live2d_model(tmp_path):
    assets = _write_complete_asset_sources(tmp_path)
    source = Path(assets["live2d_directory"])
    (source / "unrelated-secret.txt").write_text("do not publish", encoding="utf-8")

    CharacterCatalog(tmp_path).create({
        "id": "lantern", "name": "Lantern", "reply_language": "zh",
        "persona": "A concise persona.", "assets": assets,
        "voice": {"prompt_text": "reference", "prompt_language": "en"},
    })

    imported = tmp_path / "models" / "live2d-models" / "lantern"
    assert not (imported / "unrelated-secret.txt").exists()


@pytest.mark.parametrize("asset_name", ["avatar.moc3", "texture_00.png"])
def test_import_rejects_damaged_core_live2d_assets(tmp_path, asset_name):
    assets = _write_complete_asset_sources(tmp_path)
    (Path(assets["live2d_directory"]) / asset_name).write_bytes(b"not-real")

    with pytest.raises(ValueError, match="content does not match"):
        CharacterCatalog(tmp_path).create({
            "id": "lantern", "name": "Lantern", "reply_language": "zh",
            "persona": "A concise persona.", "assets": assets,
            "voice": {"prompt_text": "reference", "prompt_language": "en"},
        })


def test_import_rejects_truncated_checkpoint_archive(tmp_path):
    assets = _write_complete_asset_sources(tmp_path)
    Path(assets["t2s_model"]).write_bytes(b"PK\x03\x04" + b"\0" * 2048)

    with pytest.raises(ValueError, match="damaged or incomplete"):
        CharacterCatalog(tmp_path).create({
            "id": "lantern", "name": "Lantern", "reply_language": "zh",
            "persona": "A concise persona.", "assets": assets,
            "voice": {"prompt_text": "reference", "prompt_language": "en"},
        })


def _install_system_model(tmp_path: Path, model_id: str = "testmodel") -> None:
    """Drop a minimal Live2D model directory into the system model library."""
    model_dir = tmp_path / "models" / "live2d-models" / model_id
    model_dir.mkdir(parents=True)
    (model_dir / f"{model_id}.model3.json").write_text(json.dumps({
        "Version": 3,
        "FileReferences": {"Moc": "test.moc3", "Textures": ["texture_00.png"]},
    }), encoding="utf-8")
    (model_dir / "test.moc3").write_bytes(b"MOC3\x04" + b"\0" * 2048)
    (model_dir / "texture_00.png").write_bytes(b"png")


def _install_system_voice(tmp_path: Path, voice_id: str = "testvoice") -> None:
    assets = _write_complete_asset_sources(tmp_path)
    VoiceRegistry(tmp_path).add({
        "id": voice_id,
        "name": "Test Voice",
        "prompt_text": "reference",
        "prompt_lang": "en",
        "reference_audio": assets["reference_audio"],
        "t2s_model": assets["t2s_model"],
        "vits_model": assets["vits_model"],
    })


def test_reference_character_creation_writes_only_a_thin_card(tmp_path):
    _install_system_model(tmp_path)
    _install_system_voice(tmp_path)
    catalog = CharacterCatalog(tmp_path)

    created = catalog.create({
        "id": "lantern",
        "name": "Lantern",
        "persona": "A concise persona.",
        "reply_language": "zh",
        "model_id": "testmodel",
        "voice_id": "testvoice",
    })

    assert created == {
        "id": "lantern",
        "name": "Lantern",
        "reply_language": "zh",
        "live2d_model": "testmodel",
        "voice_configured": True,
    }

    character_dir = tmp_path / "config" / "characters" / "lantern"
    card = json.loads((character_dir / "character.json").read_text("utf-8"))
    assert card["live2d"]["model"] == "testmodel"
    assert card["tts"]["voice_id"] == "testvoice"
    # No assets were copied into the character directory.
    assert not (character_dir / "model").exists()
    assert not (tmp_path / "models" / "live2d-models" / "lantern").exists()
    # Reference creation must not fabricate a model registry entry or profile.
    live2d_config_path = tmp_path / "config" / "live2d_models.json"
    assert not live2d_config_path.exists()
    assert not (tmp_path / "config" / "avatar_profiles" / "lantern.json").exists()
    # Index still records the character.
    index = yaml.safe_load(
        (tmp_path / "config" / "characters" / "index.yaml").read_text("utf-8")
    )
    assert any(item["id"] == "lantern" for item in index["characters"])


def test_reference_character_rejects_missing_model_or_voice(tmp_path):
    _install_system_model(tmp_path)
    catalog = CharacterCatalog(tmp_path)

    with pytest.raises(ValueError, match="model is not installed"):
        catalog.create({
            "id": "lantern", "name": "Lantern", "persona": "persona",
            "reply_language": "zh", "model_id": "ghost", "voice_id": "testvoice",
        })
    _install_system_voice(tmp_path)
    with pytest.raises(ValueError, match="voice is not installed"):
        catalog.create({
            "id": "lantern", "name": "Lantern", "persona": "persona",
            "reply_language": "zh", "model_id": "testmodel", "voice_id": "ghost",
        })
    assert not (tmp_path / "config" / "characters" / "lantern").exists()


def test_register_model_backfills_side_registries(tmp_path):
    _install_system_model(tmp_path)
    catalog = CharacterCatalog(tmp_path)

    result = catalog.register_model("testmodel")
    assert result["id"] == "testmodel"

    live2d_config = json.loads(
        (tmp_path / "config" / "live2d_models.json").read_text("utf-8")
    )
    assert "testmodel" in live2d_config
    profile = json.loads(
        (tmp_path / "config" / "avatar_profiles" / "testmodel.json").read_text("utf-8")
    )
    assert profile["model"] == "testmodel"
    # Idempotent.
    catalog.register_model("testmodel")
    assert "testmodel" in json.loads(
        (tmp_path / "config" / "live2d_models.json").read_text("utf-8")
    )


def test_management_api_lists_models_and_registers_model(tmp_path):
    _install_system_model(tmp_path)
    manager = RuntimeManager(base_dir=tmp_path, runtime=_Runtime())
    handler = ManagementHandler()
    handler._manager = manager

    before = asyncio.run(handler.handle("get_model_catalog", {}, "m-1"))[0]
    assert before.payload.data == {"models": [{
        "id": "testmodel", "has_model3": True, "profile": False,
    }]}

    registered = asyncio.run(handler.handle(
        "register_model", {"model_id": "testmodel"}, "m-2"
    ))[0]
    assert registered.payload.data["model"]["id"] == "testmodel"

    after = asyncio.run(handler.handle("get_model_catalog", {}, "m-3"))[0]
    assert after.payload.data["models"][0]["profile"] is True


def test_management_api_lists_and_adds_voice_packs(tmp_path):
    assets = _write_complete_asset_sources(tmp_path)
    manager = RuntimeManager(base_dir=tmp_path, runtime=_Runtime())
    handler = ManagementHandler()
    handler._manager = manager

    before = asyncio.run(handler.handle("get_voice_catalog", {}, "v-1"))[0]
    assert before.payload.data == {"voices": []}

    added = asyncio.run(handler.handle("add_voice", {
        "id": "monika", "name": "Monika",
        "prompt_text": "reference", "prompt_lang": "en",
        "reference_audio": assets["reference_audio"],
        "t2s_model": assets["t2s_model"],
        "vits_model": assets["vits_model"],
    }, "v-2"))[0]
    assert added.payload.data["voice"]["id"] == "monika"

    after = asyncio.run(handler.handle("get_voice_catalog", {}, "v-3"))[0]
    assert after.payload.data["voices"] == [added.payload.data["voice"]]


def test_persist_default_updates_index_yaml(tmp_path):
    _install_system_model(tmp_path)
    _install_system_voice(tmp_path)
    catalog = CharacterCatalog(tmp_path)
    catalog.create({
        "id": "monika", "name": "Monika", "persona": "persona",
        "reply_language": "en", "model_id": "testmodel", "voice_id": "testvoice",
    })
    catalog.create({
        "id": "alice", "name": "Alice", "persona": "persona",
        "reply_language": "zh", "model_id": "testmodel", "voice_id": "testvoice",
    })

    # First created character becomes the default.
    index = yaml.safe_load(
        (tmp_path / "config" / "characters" / "index.yaml").read_text("utf-8")
    )
    assert index["default"] == "monika"

    catalog.persist_default("alice")
    index = yaml.safe_load(
        (tmp_path / "config" / "characters" / "index.yaml").read_text("utf-8")
    )
    assert index["default"] == "alice"


def test_delete_character_removes_only_role_definition_and_updates_default(tmp_path):
    _install_system_model(tmp_path)
    _install_system_voice(tmp_path)
    catalog = CharacterCatalog(tmp_path)
    for character_id in ("monika", "alice"):
        catalog.create({
            "id": character_id,
            "name": character_id.title(),
            "persona": "persona",
            "reply_language": "zh",
            "model_id": "testmodel",
            "voice_id": "testvoice",
        })

    deleted = catalog.delete("monika")

    assert deleted["fallback_character_id"] == "alice"
    assert not (tmp_path / "config" / "characters" / "monika").exists()
    assert (tmp_path / "models" / "live2d-models" / "testmodel").exists()
    assert (tmp_path / "config" / "voices" / "testvoice" / "voice.json").exists()
    index = yaml.safe_load(
        (tmp_path / "config" / "characters" / "index.yaml").read_text("utf-8")
    )
    assert index["default"] == "alice"
    assert [item["id"] for item in index["characters"]] == ["alice"]


def test_delete_character_rejects_last_role(tmp_path):
    _install_system_model(tmp_path)
    _install_system_voice(tmp_path)
    catalog = CharacterCatalog(tmp_path)
    catalog.create({
        "id": "monika", "name": "Monika", "persona": "persona",
        "reply_language": "zh", "model_id": "testmodel", "voice_id": "testvoice",
    })

    with pytest.raises(ValueError, match="last character"):
        catalog.delete("monika")
    # Idempotent.
    catalog.persist_default("alice")
    index = yaml.safe_load(
        (tmp_path / "config" / "characters" / "index.yaml").read_text("utf-8")
    )
    assert index["default"] == "alice"


def test_management_delete_character_switches_active_and_cleans_owned_state(
    tmp_path, monkeypatch,
):
    _install_system_model(tmp_path)
    _install_system_voice(tmp_path)
    catalog = CharacterCatalog(tmp_path)
    for character_id in ("monika", "alice"):
        catalog.create({
            "id": character_id,
            "name": character_id.title(),
            "persona": "persona",
            "reply_language": "zh",
            "model_id": "testmodel",
            "voice_id": "testvoice",
        })

    store = MemoryStore(base_dir=tmp_path)

    class _MemoryProvider:
        _store = store

    class _RoleRuntime:
        def __init__(self):
            self.active_id = "monika"
            self.providers = {"memory": _MemoryProvider()}
            self._character_registry = CharacterRegistry(tmp_path)
            self._conversations_by_character = {"monika": object(), "alice": object()}

        def get_character_info(self):
            card = self._character_registry.get(self.active_id)
            return {"card": card, "name": card["name"]["zh"]}

        def switch_character(self, character_id):
            self._character_registry.refresh()
            self._character_registry.activate(character_id)
            self.active_id = character_id
            return {"character_id": character_id}

    runtime = _RoleRuntime()
    manager = RuntimeManager(base_dir=tmp_path, runtime=runtime)
    manager.set_prompt_config(
        "monika", {"persona": {"mode": "replace", "content": "custom"}},
        "addition",
    )
    store.upsert_memory(
        memory_type="fact", subject="user", predicate="name",
        content="monika memory", character_id="monika",
        stable_key="fact:user:name",
    )
    history_uid = manager.create_history()["history_uid"]
    manager.record_turn_metadata(history_uid, "monika history")
    monkeypatch.setattr(compiler_mod, "_get_base", lambda: tmp_path)
    compiled = tmp_path / "data" / "memory" / "compiled" / "monika"
    compiled.mkdir(parents=True)
    (compiled / "memory.md").write_text("compiled", encoding="utf-8")

    handler = ManagementHandler()
    handler._manager = manager
    event = asyncio.run(handler.handle(
        "delete_character", {"character_id": "monika"}, "delete-1"
    ))[0]

    assert event.payload.data["active_character_id"] == "alice"
    assert event.payload.data["shared_assets_preserved"] is True
    assert not (tmp_path / "config" / "characters" / "monika").exists()
    assert (tmp_path / "models" / "live2d-models" / "testmodel").exists()
    assert not (tmp_path / "data" / "prompts" / "monika.json").exists()
    assert not (tmp_path / "data" / "prompts" / "monika.md").exists()
    assert not compiled.exists()
    assert store.list_memories(character_id="monika") == []
    assert history_uid not in manager._history_index
    assert "monika" not in runtime._conversations_by_character


def test_character_detail_exposes_only_safe_editing_metadata(tmp_path):
    _install_system_model(tmp_path)
    _install_system_voice(tmp_path)
    catalog = CharacterCatalog(tmp_path)
    catalog.create({
        "id": "lantern", "name": "Lantern", "persona": "persona",
        "reply_language": "zh", "model_id": "testmodel", "voice_id": "testvoice",
    })

    assert catalog.get("lantern") == {
        "id": "lantern",
        "name": "Lantern",
        "persona": "persona",
        "personality_profile": {},
        "reply_language": "zh",
        "model_id": "testmodel",
        "voice_id": "testvoice",
        "voice_name": "Test Voice",
        "resource_mode": "reference",
        "resource_references_editable": True,
        "live2d_model": "testmodel",
        "voice_configured": True,
    }


def test_character_personality_profile_round_trips_without_rebuilding_card(tmp_path):
    _install_system_model(tmp_path)
    _install_system_voice(tmp_path)
    catalog = CharacterCatalog(tmp_path)
    catalog.create({
        "id": "lantern", "name": "Lantern", "persona": "persona",
        "reply_language": "zh", "model_id": "testmodel", "voice_id": "testvoice",
        "personality_profile": {
            "values": ["honesty"],
            "speech_style": {"tone": ["warm"], "avoid": ["stage directions"]},
        },
    })
    card_path = tmp_path / "config" / "characters" / "lantern" / "character.json"
    card = json.loads(card_path.read_text("utf-8"))
    card["future_extension"] = {"keep": True}
    card_path.write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")

    created_profile = catalog.get("lantern")["personality_profile"]
    assert created_profile["values"] == ["honesty"]
    assert created_profile["speech_style"] == {
        "tone": ["warm"], "habits": [], "avoid": ["stage directions"],
    }

    detail = catalog.update("lantern", {
        "personality_profile": {
            "motivations": ["help the user"],
            "relationship_style": {"close": "playful and candid"},
        },
    })

    stored = json.loads(card_path.read_text("utf-8"))
    assert detail["personality_profile"]["motivations"] == ["help the user"]
    assert detail["personality_profile"]["relationship_style"]["close"] == (
        "playful and candid"
    )
    assert stored["personality_profile"] == detail["personality_profile"]
    assert stored["future_extension"] == {"keep": True}


def test_reference_character_update_preserves_unedited_card_and_index_fields(tmp_path):
    _install_system_model(tmp_path)
    _install_system_voice(tmp_path)
    catalog = CharacterCatalog(tmp_path)
    catalog.create({
        "id": "lantern", "name": "Lantern", "persona": "original persona",
        "reply_language": "zh", "model_id": "testmodel", "voice_id": "testvoice",
    })
    card_path = tmp_path / "config" / "characters" / "lantern" / "character.json"
    card = json.loads(card_path.read_text("utf-8"))
    card["future_extension"] = {"keep": True}
    card["live2d"]["future_binding"] = "keep"
    card["tts"]["future_voice_option"] = "keep"
    card_path.write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")
    index_path = tmp_path / "config" / "characters" / "index.yaml"
    index = yaml.safe_load(index_path.read_text("utf-8"))
    index["characters"][0]["future_index_option"] = "keep"
    index_path.write_text(yaml.safe_dump(index, sort_keys=False), encoding="utf-8")

    updated = catalog.update("lantern", {
        "name": "Lantern Prime",
        "persona": "updated persona",
        "reply_language": "ja",
        "model_id": "testmodel",
        "voice_id": "testvoice",
    })

    stored = json.loads(card_path.read_text("utf-8"))
    stored_index = yaml.safe_load(index_path.read_text("utf-8"))
    assert updated["name"] == "Lantern Prime"
    assert stored["id"] == "lantern"
    assert stored["character_setting"] == "updated persona"
    assert stored["identity"] == "original persona"
    assert stored["future_extension"] == {"keep": True}
    assert stored["live2d"]["future_binding"] == "keep"
    assert stored["tts"]["future_voice_option"] == "keep"
    assert stored_index["characters"][0]["name"] == "Lantern Prime"
    assert stored_index["characters"][0]["future_index_option"] == "keep"


def test_embedded_character_update_locks_resources_and_preserves_pack_fields(tmp_path):
    assets = _write_complete_asset_sources(tmp_path)
    catalog = CharacterCatalog(tmp_path)
    catalog.create({
        "id": "lantern", "name": "Lantern", "reply_language": "zh",
        "persona": "original persona", "assets": assets,
        "voice": {"prompt_text": "reference", "prompt_language": "en"},
    })
    before = json.loads(
        (tmp_path / "config" / "characters" / "lantern" / "character.json")
        .read_text("utf-8")
    )

    detail = catalog.update("lantern", {
        "name": "Lantern Prime", "persona": "updated persona",
        "reply_language": "ja",
    })
    after = json.loads(
        (tmp_path / "config" / "characters" / "lantern" / "character.json")
        .read_text("utf-8")
    )

    assert detail["resource_mode"] == "embedded"
    assert detail["resource_references_editable"] is False
    assert after["tts"] == before["tts"]
    assert after["live2d"] == before["live2d"]
    assert after["rules"] == before["rules"]
    with pytest.raises(ValueError, match="embedded character resources are read-only"):
        catalog.update("lantern", {"model_id": "another-model"})


def test_character_update_rejects_id_and_unknown_fields(tmp_path):
    _install_system_model(tmp_path)
    _install_system_voice(tmp_path)
    catalog = CharacterCatalog(tmp_path)
    catalog.create({
        "id": "lantern", "name": "Lantern", "persona": "persona",
        "reply_language": "zh", "model_id": "testmodel", "voice_id": "testvoice",
    })

    with pytest.raises(ValueError, match="character id is read-only"):
        catalog.update("lantern", {"id": "renamed"})
    with pytest.raises(ValueError, match="unsupported character update fields"):
        catalog.update("lantern", {"rules": {"avoid": []}})


def test_character_update_restores_card_and_index_when_index_write_fails(
    tmp_path, monkeypatch,
):
    _install_system_model(tmp_path)
    _install_system_voice(tmp_path)
    catalog = CharacterCatalog(tmp_path)
    catalog.create({
        "id": "lantern", "name": "Lantern", "persona": "persona",
        "reply_language": "zh", "model_id": "testmodel", "voice_id": "testvoice",
    })
    card_path = tmp_path / "config" / "characters" / "lantern" / "character.json"
    index_path = tmp_path / "config" / "characters" / "index.yaml"
    previous_card = card_path.read_bytes()
    previous_index = index_path.read_bytes()
    real_atomic_text = catalog._atomic_text

    def fail_index(path, content):
        if path == index_path:
            raise OSError("index locked")
        return real_atomic_text(path, content)

    monkeypatch.setattr(catalog, "_atomic_text", fail_index)
    with pytest.raises(OSError, match="index locked"):
        catalog.update("lantern", {"name": "Broken Update"})

    assert card_path.read_bytes() == previous_card
    assert index_path.read_bytes() == previous_index


def test_management_character_detail_reports_persona_override(tmp_path):
    _install_system_model(tmp_path)
    _install_system_voice(tmp_path)
    catalog = CharacterCatalog(tmp_path)
    catalog.create({
        "id": "lantern", "name": "Lantern", "persona": "persona",
        "reply_language": "zh", "model_id": "testmodel", "voice_id": "testvoice",
    })
    manager = RuntimeManager(base_dir=tmp_path, runtime=_Runtime())
    manager.set_prompt_config(
        "lantern", {"persona": {"mode": "replace", "content": "override"}}, "",
    )
    handler = ManagementHandler()
    handler._manager = manager

    event = asyncio.run(handler.handle(
        "get_character_detail", {"character_id": "lantern"}, "detail-1",
    ))[0]

    assert event.payload.data["character"]["persona_override_active"] is True


def test_management_updates_current_character_through_existing_reload_chain(tmp_path):
    _install_system_model(tmp_path)
    _install_system_voice(tmp_path)
    catalog = CharacterCatalog(tmp_path)
    catalog.create({
        "id": "monika", "name": "Monika", "persona": "old persona",
        "reply_language": "en", "model_id": "testmodel", "voice_id": "testvoice",
    })

    class _EditableRuntime:
        def __init__(self):
            self._runtime_idle = True
            self._character_registry = CharacterRegistry(tmp_path)
            self._conversations_by_character = {"monika": object()}
            self.providers = {}
            self.switches = []

        def get_character_info(self):
            card = self._character_registry.get("monika")
            return {"card": card, "name": card["name"]["zh"]}

        def switch_character(self, character_id):
            self.switches.append(character_id)
            self._character_registry.refresh()
            self._character_registry.activate(character_id)
            return {"character_id": character_id}

    runtime = _EditableRuntime()
    manager = RuntimeManager(base_dir=tmp_path, runtime=runtime)
    handler = ManagementHandler()
    handler._manager = manager

    event = asyncio.run(handler.handle("update_character", {
        "character_id": "monika", "name": "Monika Prime",
        "persona": "new persona", "reply_language": "ja",
        "model_id": "testmodel", "voice_id": "testvoice",
    }, "update-1"))[0]

    assert runtime.switches == ["monika"]
    assert event.payload.data["runtime_reloaded"] is True
    assert event.payload.data["character"]["name"] == "Monika Prime"
    assert runtime.get_character_info()["card"]["character_setting"] == "new persona"


def test_management_rejects_busy_current_character_update_without_disk_changes(tmp_path):
    _install_system_model(tmp_path)
    _install_system_voice(tmp_path)
    catalog = CharacterCatalog(tmp_path)
    catalog.create({
        "id": "monika", "name": "Monika", "persona": "old persona",
        "reply_language": "en", "model_id": "testmodel", "voice_id": "testvoice",
    })
    card_path = tmp_path / "config" / "characters" / "monika" / "character.json"
    previous = card_path.read_bytes()

    class _BusyRuntime:
        _runtime_idle = False

        def get_character_info(self):
            return {"card": {"id": "monika"}, "name": "Monika"}

    manager = RuntimeManager(base_dir=tmp_path, runtime=_BusyRuntime())
    handler = ManagementHandler()
    handler._manager = manager
    event = asyncio.run(handler.handle("update_character", {
        "character_id": "monika", "name": "Should Not Persist",
    }, "update-busy"))[0]

    assert event.event_type == "management.failed"
    assert event.payload.code == "character_edit_failed"
    assert "processing a turn" in event.payload.message
    assert card_path.read_bytes() == previous


def test_management_updates_non_current_character_without_switching_runtime(tmp_path):
    _install_system_model(tmp_path)
    _install_system_voice(tmp_path)
    catalog = CharacterCatalog(tmp_path)
    for character_id in ("monika", "alice"):
        catalog.create({
            "id": character_id, "name": character_id.title(), "persona": "old persona",
            "reply_language": "en", "model_id": "testmodel", "voice_id": "testvoice",
        })

    class _NonCurrentRuntime:
        _runtime_idle = True

        def __init__(self):
            self._character_registry = CharacterRegistry(tmp_path)
            self.switches = []

        def get_character_info(self):
            return {"card": self._character_registry.get("monika"), "name": "Monika"}

        def switch_character(self, character_id):
            self.switches.append(character_id)
            return {"character_id": character_id}

    runtime = _NonCurrentRuntime()
    manager = RuntimeManager(base_dir=tmp_path, runtime=runtime)

    result = manager.update_character("alice", {
        "name": "Alice Prime", "persona": "new persona", "reply_language": "zh",
    })

    assert runtime.switches == []
    assert result["runtime_reloaded"] is False
    assert result["active_character_id"] == "monika"
    assert runtime._character_registry.get("alice")["character_setting"] == "new persona"


def test_management_restores_current_character_when_runtime_reload_fails(tmp_path):
    _install_system_model(tmp_path)
    _install_system_voice(tmp_path)
    catalog = CharacterCatalog(tmp_path)
    catalog.create({
        "id": "monika", "name": "Monika", "persona": "old persona",
        "reply_language": "en", "model_id": "testmodel", "voice_id": "testvoice",
    })
    card_path = tmp_path / "config" / "characters" / "monika" / "character.json"
    index_path = tmp_path / "config" / "characters" / "index.yaml"
    previous_card = card_path.read_bytes()
    previous_index = index_path.read_bytes()

    class _FailingRuntime:
        _runtime_idle = True

        def __init__(self):
            self._character_registry = CharacterRegistry(tmp_path)

        def get_character_info(self):
            return {"card": self._character_registry.get("monika"), "name": "Monika"}

        def switch_character(self, character_id):
            return {"character_id": character_id, "error": "restore failed"}

    manager = RuntimeManager(base_dir=tmp_path, runtime=_FailingRuntime())

    with pytest.raises(RuntimeError, match="restore failed"):
        manager.update_character("monika", {
            "name": "Should Roll Back", "persona": "new persona",
            "reply_language": "ja",
        })

    assert card_path.read_bytes() == previous_card
    assert index_path.read_bytes() == previous_index


def test_reference_character_update_validates_replacement_resources(tmp_path):
    _install_system_model(tmp_path)
    _install_system_voice(tmp_path)
    catalog = CharacterCatalog(tmp_path)
    catalog.create({
        "id": "lantern", "name": "Lantern", "persona": "persona",
        "reply_language": "zh", "model_id": "testmodel", "voice_id": "testvoice",
    })
    card_path = tmp_path / "config" / "characters" / "lantern" / "character.json"
    previous = card_path.read_bytes()

    with pytest.raises(ValueError, match="model is not installed"):
        catalog.update("lantern", {"model_id": "missing-model"})
    with pytest.raises(ValueError, match="voice is not installed"):
        catalog.update("lantern", {"voice_id": "missing-voice"})

    assert card_path.read_bytes() == previous
