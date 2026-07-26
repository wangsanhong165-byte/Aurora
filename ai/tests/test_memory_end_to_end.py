import asyncio

from app.character.registry import CharacterRegistry
from app.domain.character.character import Character
from app.providers.memory.sqlite_memory import SQLiteMemory


def run(coro):
    return asyncio.run(coro)


def test_preference_learn_restart_and_paraphrased_recall(tmp_path):
    memory = SQLiteMemory()
    from app.memory.store import MemoryStore
    memory._store = MemoryStore(base_dir=tmp_path)
    card = CharacterRegistry().active
    character = Character(card)

    run(memory.store("conversation_turn", {
        "user": "我最喜欢巧克力蛋糕",
        "assistant": "记住了。",
        "character_id": character.id,
        "character": character,
    }))

    restarted = Character(card)
    memory.restore_character(restarted)
    recalled = run(memory.retrieve(
        "你知道我爱吃什么吗", character_id=restarted.id, limit=10
    ))

    assert restarted.preferences.get("巧克力蛋糕") is not None
    assert any(
        "巧克力蛋糕" in item.get("data", {}).get("content", "")
        for item in recalled
    )


def test_long_history_soft_budget_stabilizes():
    from app.runtime.context_budget import ContextBudget
    budget = ContextBudget(soft_tokens=3000, hard_tokens=6000)
    fixed = [
        {"role": "system", "content": "PERSONA_CORE " + "人格" * 500},
        {"role": "system", "content": "IMPORTANT_MEMORY " + "记忆" * 500},
    ]
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": "长期对话" * 300}
        for i in range(1000)
    ]
    fitted, report = budget.fit_messages(fixed + history + [
        {"role": "user", "content": "当前问题"}
    ])
    text = "\n".join(str(message["content"]) for message in fitted)

    assert report["estimated_tokens"] <= budget.hard_tokens
    assert "PERSONA_CORE" in text
    assert "IMPORTANT_MEMORY" in text
    assert "当前问题" in text
