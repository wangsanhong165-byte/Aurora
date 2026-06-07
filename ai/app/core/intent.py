"""Initiative decision engine — computes candidates from state, picks the best.

Pure-logic layer between trigger and LLM. No LLM calls here.
Uses existing MentalState, FocusStore, RelationshipMemory to decide
WHY Monika should speak, not just WHEN.
"""

from __future__ import annotations

from typing import Any


def compute_candidates(
    idle_sec: float,
    mental_state: Any,     # MentalState (mood/curiosity/attachment)
    focus_store: Any,      # FocusStore (topic tracking)
    relationship: Any,     # RelationshipMemory (trust/familiarity/respect/concern)
    events: list | None = None,   # InitiativeEvent list from checker
    context: dict | None = None,  # state_store.snapshot() for screen awareness
) -> list[dict[str, Any]]:
    """Generate initiative candidates from current companion state.

    Each candidate has:
      type:   follow_up | curiosity | care | presence_check | share_thought
      topic:  what to talk about (from focus/memory)
      score:  0.0~1.0 confidence
    """
    candidates: list[dict[str, Any]] = []
    activity = (context or {}).get("activity", "idle")

    # -- Debug: dump state
    focus_top = focus_store.top(3)
    event_types = [e.type for e in events] if events else []
    print(f"[Intent] idle={idle_sec:.0f}s mood={mental_state.mood:.0f} cur={mental_state.curiosity:.0f} att={mental_state.attachment:.0f} conc={relationship.concern:.0f} focus={focus_top} activity={activity} events={event_types}")

    # --- follow_up: active focus topics we haven't resolved ---
    active_topics = focus_top
    if active_topics:
        curiosity_factor = mental_state.curiosity / 100
        weight = curiosity_factor * 0.7 + 0.3
        candidates.append({
            "type": "follow_up",
            "topic": active_topics[0],
            "score": round(0.75 * weight, 2),
        })

    # --- curiosity: high curiosity + has topics ---
    if mental_state.curiosity > 55 and active_topics:
        candidates.append({
            "type": "curiosity",
            "topic": active_topics[0],
            "score": round(min(mental_state.curiosity / 130, 0.65), 2),
        })

    # --- care: low mood (user might be struggling) + Monika cares ---
    if mental_state.mood < 48 and relationship.concern > 45:
        candidates.append({
            "type": "care",
            "topic": "user_wellbeing",
            "score": round(0.55 * (relationship.concern / 100), 2),
        })

    # --- presence_check: very long idle ---
    if idle_sec > 480:  # 8 min
        idle_factor = min(idle_sec / 3600, 1.0)  # saturates at 1h
        candidates.append({
            "type": "presence_check",
            "topic": "user_availability",
            "score": round(0.30 + idle_factor * 0.20, 2),
        })

    # --- context_aware: screen activity changed to something notable ---
    meaningful_activities = {"coding", "writing", "gaming", "browsing", "chatting"}
    if activity in meaningful_activities:
        app_name = (context or {}).get("context", activity)
        candidates.append({
            "type": "curiosity",
            "topic": f"user is {activity} ({app_name})",
            "score": 0.38,
        })

    # --- event bonus: screen_change or idle_timeout from InitiativeChecker ---
    has_screen_change = any(e.type == "screen_change" for e in events) if events else False
    has_idle_timeout = any(e.type == "idle_timeout" for e in events) if events else False
    for c in candidates:
        if has_screen_change and c["type"] in ("curiosity", "context_aware"):
            c["score"] = round(min(c["score"] + 0.06, 0.75), 2)
        if has_idle_timeout and c["type"] in ("presence_check", "follow_up"):
            c["score"] = round(min(c["score"] + 0.08, 0.75), 2)

    # --- idle_greeting: no focus topics, moderate idle ---
    if not candidates and idle_sec > 360:
        candidates.append({
            "type": "follow_up",
            "topic": "check_in",
            "score": round(0.35 + min(idle_sec / 3600 * 0.15, 0.15), 2),
        })

    # --- share_thought: good mood, Monika wants to share ---
    if mental_state.mood > 62 and mental_state.attachment > 25:
        candidates.append({
            "type": "share_thought",
            "topic": "daily_reflection",
            "score": round((mental_state.mood / 100) * 0.4, 2),
        })

    return candidates


def decide_action(
    candidates: list[dict[str, Any]],
    threshold: float = 0.30,
) -> dict[str, Any] | None:
    """Pick the best candidate above threshold.

    Returns {type, topic, score} or None if no candidate qualifies.
    """
    if not candidates:
        return None
    best = max(candidates, key=lambda c: c["score"])
    if best["score"] < threshold:
        return None
    return best


def describe_candidate(candidate: dict[str, Any]) -> str:
    """Human-readable reason for logging."""
    labels = {
        "follow_up": "follow-up on topic",
        "curiosity": "curious about topic",
        "care": "checking on user",
        "presence_check": "long idle, checking in",
        "share_thought": "wants to share a thought",
    }
    label = labels.get(candidate["type"], candidate["type"])
    return f"{label}: {candidate['topic']} (score={candidate['score']:.2f})"
