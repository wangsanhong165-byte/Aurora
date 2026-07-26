from app.runtime.initiative import InitiativeCandidate, InitiativeQueue


def _candidate(topic, priority, created_at, ttl=60):
    return InitiativeCandidate.create(
        source="test",
        topic=topic,
        priority=priority,
        freshness=1.0,
        ttl_seconds=ttl,
        created_at=created_at,
        payload={"topic": topic},
    )


def test_queue_deduplicates_topic_and_keeps_newer_higher_candidate():
    queue = InitiativeQueue()
    queue.enqueue(_candidate("drink water", 0.4, 10))
    queue.enqueue(_candidate("  Drink   Water ", 0.8, 11))

    assert len(queue) == 1
    assert queue.pop_next(now=12).priority == 0.8


def test_queue_discards_expired_candidates():
    queue = InitiativeQueue()
    queue.enqueue(_candidate("old", 1.0, 10, ttl=2))

    assert queue.pop_next(now=13) is None


def test_queue_only_pops_when_runtime_is_idle():
    queue = InitiativeQueue()
    queue.enqueue(_candidate("hello", 1.0, 10))

    assert queue.pop_next(now=11, runtime_idle=False) is None
    assert len(queue) == 1
    assert queue.pop_next(now=11, runtime_idle=True).topic == "hello"
