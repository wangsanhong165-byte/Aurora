"""Initiative decision engine - simplified.

Pure-logic layer between trigger and LLM. No LLM calls here.
Uses mood + idle time + activity to decide WHY Monika should speak.
No longer depends on FocusStore, RelationshipMemory, or MentalState curiosity/attachment.
"""

from __future__ import annotations

from typing import Any


def compute_candidates(
    idle_sec: float,
    mood: float,
    activity: str = "idle",
    events: list | None = None,
) -> list[dict[str, Any]]:
    """Generate initiative candidates from current companion state."""
    candidates: list[dict[str, Any]] = []

    event_types = [e.type for e in events] if events else []
    print(f"[Intent] idle={idle_sec:.0f}s mood={mood:.0f} activity={activity} events={event_types}")

    if mood < 48:
        candidates.append({
            "type": "care",
            "topic": "user_wellbeing",
            "score": round(0.50 * (1.0 - mood / 100), 2),
        })

    if idle_sec > 480:
        idle_factor = min(idle_sec / 3600, 1.0)
        candidates.append({
            "type": "presence_check",
            "topic": "user_availability",
            "score": round(0.30 + idle_factor * 0.20, 2),
        })

    meaningful_activities = {"coding", "writing", "gaming", "browsing", "chatting"}
    if activity in meaningful_activities:
        candidates.append({
            "type": "curiosity",
            "topic": f"user is {activity}",
            "score": 0.38,
        })

    has_screen_change = any(e.type == "screen_change" for e in events) if events else False
    has_idle_timeout = any(e.type == "idle_timeout" for e in events) if events else False
    for c in candidates:
        if has_screen_change and c["type"] in ("curiosity",):
            c["score"] = round(min(c["score"] + 0.06, 0.75), 2)

    # ── idle_timeout fires when user idle exceeds threshold (default 300s, UI-configurable) ──
    if has_idle_timeout:
        candidates.append({
            "type": "idle_greeting",
            "topic": "user_availability",
            "score": 0.42,  # Above the 0.30 threshold — reliably triggers
        })

    if not candidates and idle_sec > 120:
        candidates.append({
            "type": "follow_up",
            "topic": "check_in",
            "score": round(0.35 + min(idle_sec / 3600 * 0.15, 0.15), 2),
        })

    if mood > 62:
        candidates.append({
            "type": "share_thought",
            "topic": "daily_reflection",
            "score": round((mood / 100) * 0.35, 2),
        })

    return candidates


def decide_action(
    candidates: list[dict[str, Any]],
    threshold: float = 0.30,
) -> dict[str, Any] | None:
    """Pick the best candidate above threshold."""
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
