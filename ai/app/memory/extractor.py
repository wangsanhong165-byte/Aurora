"""Memory extractor — rolling summary + fact extraction.

Background pipeline. Character-agnostic: accepts character_name parameter
so the same pipeline works for any persona.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from app.memory.store import memory_store
from app.memory.prompts import (
    system_rolling_summary,
    system_fact_extraction,
)

_TURNS_PER_SUMMARY = 10


def _call_llm(system: str, user: str, llm_adapter: Any, timeout: int = 15) -> str:
    if not llm_adapter:
        return ""
    return llm_adapter.generate_text(
        system=system,
        user=user,
        temperature=0.3,
        max_tokens=1024,
        timeout=timeout,
    )


def run_rolling_summary(llm_adapter: Any, character_name: str = "") -> str:
    """Summarize recent conversation turns into 2-3 sentences."""
    turns = memory_store.recent_turns(_TURNS_PER_SUMMARY * 2)
    if not turns or len(turns) < 3:
        return ""

    lines = []
    for t in turns:
        role = t.get("role", "")
        content = str(t.get("content", "")).strip()
        if not content:
            continue
        label = "用户" if role == "user" else (character_name or "AI")
        lines.append(f"{label}: {content}")

    conv_text = "\n".join(lines)
    if len(conv_text) < 20:
        return ""

    return _call_llm(system_rolling_summary(character_name), conv_text, llm_adapter)


def extract_facts(
    summary: str, llm_adapter: Any, character_id: str = ""
) -> list[dict]:
    """Split a summary into atomic facts with tags."""
    if not summary or len(summary) < 10:
        return []

    result = _call_llm(system_fact_extraction(), summary, llm_adapter, timeout=20)
    if not result:
        return []

    result = result.strip()
    if result.startswith("```"):
        lines = result.split("\n")
        result = "\n".join(l for l in lines if not l.strip().startswith("```"))

    try:
        facts = json.loads(result)
    except json.JSONDecodeError:
        import re
        match = re.search(r"\[.*?\]", result, re.DOTALL)
        if match:
            try:
                facts = json.loads(match.group(0))
            except (json.JSONDecodeError, TypeError):
                return []
        else:
            return []

    if not isinstance(facts, list):
        return []

    stored = []
    structured_candidates = []
    for f in facts:
        if not isinstance(f, dict):
            continue
        content = str(f.get("fact", "")).strip()
        if not content or len(content) < 5:
            continue
        tags = f.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        time_val = f.get("time")
        ok = memory_store.add_fact(
            content=content,
            tags=[str(t) for t in tags if isinstance(t, str)],
            importance=0.6,
            source="auto_extract",
            time=str(time_val) if time_val else None,
            character_id=character_id,
        )
        if ok:
            stored.append(content)
        structured_candidates.append(f)

    # Structured lifecycle is independent from the legacy facts table so
    # conflicting values can supersede old ones instead of being rejected
    # merely because they share a broad tag.
    from app.memory.lifecycle import store_candidates
    store_candidates(memory_store, structured_candidates, character_id=character_id)

    return stored


def run_extraction_pipeline(
    llm_adapter: Any, character_name: str = "", character_id: str = ""
) -> dict:
    """Run one full extraction cycle: summary → facts."""
    stats = {"summary": "", "facts_stored": 0}

    summary = run_rolling_summary(llm_adapter, character_name)
    if not summary:
        return stats

    stats["summary"] = summary[:100]
    facts = extract_facts(summary, llm_adapter, character_id=character_id)
    stats["facts_stored"] = len(facts)

    return stats
