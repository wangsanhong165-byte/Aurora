from scripts.replay_scenarios import calculate_metrics
from scripts.assert_quality_gate import evaluate_quality_gate


def test_replay_metrics_include_latency_and_repeat_rates():
    records = [
        {"reply_text": "same", "performance": {"behavior": "speak", "emotion": "happy"}, "metrics": {"e2e_latency_ms": 100}},
        {"reply_text": "same", "performance": {"behavior": "speak", "emotion": "happy"}, "metrics": {"e2e_latency_ms": 300}},
    ]

    metrics = calculate_metrics(records)

    assert metrics["p95_latency_ms"] == 300
    assert metrics["reply_exact_repeat_rate"] == 0.5
    assert metrics["behavior_repeat_rate"] == 0.5


def test_quality_gate_reports_every_failed_threshold():
    failures = evaluate_quality_gate(
        {
            "p95_latency_ms": 5000,
            "reply_exact_repeat_rate": 0.3,
            "persona_score": 3.5,
        },
        max_p95_latency_ms=4500,
        max_repeat_rate=0.18,
        min_persona_score=4.0,
    )

    assert len(failures) == 3
