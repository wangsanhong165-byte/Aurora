from app.memory.store import MemoryStore


def test_usage_ledger_aggregates_cost_tokens_and_context(tmp_path):
    store = MemoryStore(base_dir=tmp_path)
    store.record_usage("monika", {
        "prompt_tokens": 100, "completion_tokens": 20,
        "cached_tokens": 40, "estimated_cost_usd": 0.001,
        "model": "test-model",
    }, {"estimated_tokens": 90, "compacted_messages": 2})
    store.record_usage("monika", {
        "prompt_tokens": 50, "completion_tokens": 10,
        "cached_tokens": 0, "estimated_cost_usd": 0.0005,
        "model": "test-model",
    }, {"estimated_tokens": 45})

    summary = store.usage_summary("monika")
    assert summary["totals"]["turns"] == 2
    assert summary["totals"]["prompt_tokens"] == 150
    assert summary["totals"]["completion_tokens"] == 30
    assert summary["totals"]["cached_tokens"] == 40
    assert abs(summary["totals"]["estimated_cost_usd"] - 0.0015) < 1e-9
    assert summary["recent"][1]["context_budget"]["compacted_messages"] == 2
