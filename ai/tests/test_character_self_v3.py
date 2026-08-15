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


def test_character_self_syncs_external_learning_and_records_recent_interaction():
    class Character:
        id = "monika"

        def __init__(self):
            self.state = {
                "emotion": {"current": "neutral", "intensity": 0.5},
                "mood": {"current": "neutral", "valence": 0.0, "history": []},
            }

        def dynamic_state(self):
            return self.state.copy()

        def restore_dynamic_state(self, state):
            self.state = state.copy()

    character = Character()
    aggregate = CharacterSelf(character)
    character.state["goals"] = {"active": [{"description": "记住这件事"}], "completed": []}
    aggregate.sync_from_character()
    aggregate.record_interaction(
        "我喜欢安静的界面",
        learned=[{"content": "用户喜欢安静的界面"}],
    )

    state = aggregate.snapshot()
    assert state["goals"]["active"][0]["description"] == "记住这件事"
    assert state["recent_focus"] == ["刚刚聊到：我喜欢安静的界面"]
    assert state["recent_changes"] == ["记住了：用户喜欢安静的界面"]
    assert state["interaction_count"] == 1


def test_character_self_rolls_back_all_mutations_from_a_failed_turn():
    class Character:
        id = "monika"

        def __init__(self):
            self.state = {"mood": {"current": "neutral", "valence": 0.0}}

        def dynamic_state(self):
            return self.state.copy()

        def restore_dynamic_state(self, state):
            self.state = state.copy()

    character = Character()
    aggregate = CharacterSelf(character)
    aggregate.begin_turn()
    character.state = {"mood": {"current": "happy", "valence": 0.8}}
    aggregate.sync_from_character()

    aggregate.rollback_turn()

    assert aggregate.snapshot() == {"mood": {"current": "neutral", "valence": 0.0}}
    assert character.state == aggregate.snapshot()
