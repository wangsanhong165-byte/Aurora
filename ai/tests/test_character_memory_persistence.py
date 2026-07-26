from app.character.registry import CharacterRegistry
from app.domain.character.character import Character
from app.memory.store import MemoryStore


def test_character_dynamic_state_survives_recreation(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    card = CharacterRegistry().active
    original = Character(card)
    original.relationship.update_affinity(0.2)
    original.preferences.update("编程", 0.9)
    original.goals.add("陪用户完成项目", priority=5)
    original.mood.set("playful")
    store.save_character_state(original.id, original.dynamic_state())

    restored = Character(card)
    restored.restore_dynamic_state(store.load_character_state(restored.id))

    assert restored.relationship.get_affinity() == original.relationship.get_affinity()
    assert restored.preferences.get("编程").valence == original.preferences.get("编程").valence
    assert restored.goals.top(1)[0].description == "陪用户完成项目"
    assert restored.mood.current == "playful"
