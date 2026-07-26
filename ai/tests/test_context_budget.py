from app.runtime.context_budget import ContextBudget


def test_soft_budget_preserves_important_memory_and_compacts_history():
    budget = ContextBudget(soft_tokens=350, hard_tokens=700)
    messages = [
        {"role": "system", "content": "PERSONA_CORE " + "人格" * 80},
        {"role": "system", "content": "IMPORTANT_MEMORY " + "记忆" * 80},
    ]
    messages.extend(
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"old-{i} " + "内容" * 100}
        for i in range(10)
    )
    messages.append({"role": "user", "content": "current request"})

    fitted, report = budget.fit_messages(messages)

    joined = "\n".join(str(item["content"]) for item in fitted)
    assert "PERSONA_CORE" in joined
    assert "IMPORTANT_MEMORY" in joined
    assert "current request" in joined
    assert report["compacted_messages"] > 0
    assert report["estimated_tokens"] <= budget.hard_tokens


def test_tool_result_has_anomaly_guard():
    budget = ContextBudget(tool_result_soft_chars=100, tool_result_hard_chars=180)
    text, meta = budget.fit_tool_result("x" * 1000)
    assert len(text) <= 220
    assert meta["truncated"] is True
    assert "truncated" in text.lower()


def test_hard_budget_caps_many_system_messages():
    budget = ContextBudget(soft_tokens=200, hard_tokens=400)
    messages = [
        {"role": "system", "content": f"system-{i} " + "规则" * 500}
        for i in range(8)
    ] + [{"role": "user", "content": "current"}]
    _, report = budget.fit_messages(messages)
    assert report["estimated_tokens"] <= budget.hard_tokens
