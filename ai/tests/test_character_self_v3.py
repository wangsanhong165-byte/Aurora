from app.domain.character_self import CharacterSelf


class _Character:
    id = "monika"

    def dynamic_state(self):
        return {"mood": "happy"}

    def restore_dynamic_state(self, state):
        self.restored = state


def test_character_self_only_changes_durable_state_on_explicit_commit():
    character = _Character()
    aggregate = CharacterSelf(character)

    change = aggregate.stage({"mood": "calm"})

    assert aggregate.snapshot()["mood"] == "happy"
    aggregate.commit(change)
    assert aggregate.snapshot()["mood"] == "calm"
    assert character.restored == {"mood": "calm"}


def test_character_self_commits_emotion_through_aggregate_boundary():
    character = _Character()
    character.dynamic_state = lambda: {
        "emotion": {"current": "neutral", "intensity": 0.5},
        "mood": {"current": "neutral", "valence": 0.0, "history": []},
    }
    aggregate = CharacterSelf(character)

    aggregate.commit_emotion("happy", intensity=0.8)

    assert aggregate.snapshot()["emotion"] == {
        "current": "happy",
        "intensity": 0.8,
    }
