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
_RECENT_PROMPT_MESSAGES = 10


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


def run_rolling_summary(
    llm_adapter: Any,
    character_name: str = "",
    character_id: str = "",
    store: Any = None,
    return_record: bool = False,
) -> str | tuple[str, int]:
    """Summarize recent conversation turns into 2-3 sentences (per character)."""
    store = store or memory_store
    from app.memory.compiler import get_conversation_summary_record

    existing = get_conversation_summary_record(character_id)
    turns = store.summary_window(
        character_id,
        after_log_id=int(existing.get("through_log_id", 0)),
        keep_recent=_RECENT_PROMPT_MESSAGES,
        limit=_TURNS_PER_SUMMARY * 4,
    )
    if not turns and not existing.get("content"):
        turns = store.recent_turns(
            _TURNS_PER_SUMMARY * 2, character_id=character_id
        )
    if not turns or len(turns) < 3:
        preserved = str(existing.get("content", ""))
        record = (preserved, int(existing.get("through_log_id", 0)))
        return record if return_record else preserved

    lines = []
    if existing.get("content"):
        lines.append("[Previous rolling summary]\n" + str(existing["content"]))
    for t in turns:
        role = t.get("role", "")
        content = str(t.get("content", "")).strip()
        if not content:
            continue
        label = "用户" if role == "user" else (character_name or "AI")
        lines.append(f"{label}: {content}")

    conv_text = "\n".join(lines)
    if len(conv_text) < 20:
        empty = ("", int(existing.get("through_log_id", 0)))
        return empty if return_record else ""

    result = _call_llm(system_rolling_summary(character_name), conv_text, llm_adapter)
    if not result:
        preserved = str(existing.get("content", ""))
        record = (preserved, int(existing.get("through_log_id", 0)))
        return record if return_record else preserved
    through_log_id = int(turns[-1].get("id", existing.get("through_log_id", 0)) or 0)
    return (result, through_log_id) if return_record else result


def extract_facts(
    summary: str,
    llm_adapter: Any,
    character_id: str = "",
    store: Any = None,
) -> list[dict]:
    """Split a summary into atomic facts with tags."""
    store = store or memory_store
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

    structured_candidates = []
    for f in facts:
        if not isinstance(f, dict):
            continue
        content = str(f.get("fact", "")).strip()
        if not content or len(content) < 5:
            continue
        structured_candidates.append(f)

    # ``memories`` is the canonical store.  The legacy facts table is migrated
    # at startup but no longer receives a second copy of every extraction.
    from app.memory.lifecycle import normalize_candidate
    stored_contents: list[str] = []
    for candidate in structured_candidates:
        item = normalize_candidate(candidate)
        if item is None:
            continue
        store.upsert_memory(character_id=character_id, **item)
        stored_contents.append(item["content"])
    return stored_contents


# Bound on turns fed to one extract-before-destroy pass (bulk deletes must not
# produce an oversized prompt).
_MAX_EXTRACT_TURNS = 20


def extract_from_turns(
    turns: list[dict],
    llm_adapter: Any,
    character_id: str = "",
    character_name: str = "",
    store: Any = None,
) -> dict:
    """Extract durable facts from an arbitrary turn list (extract-before-destroy).

    Used by forget() before old logs are deleted: capture what those turns
    revealed about the user before the rows disappear. Keeps only the most
    recent turns, so a bulk delete never builds an oversized prompt.
    """
    store = store or memory_store
    recent = list(turns)[-_MAX_EXTRACT_TURNS:]
    lines = []
    for t in recent:
        role = t.get("role", "")
        content = str(t.get("content", "")).strip()
        if content:
            label = "用户" if role == "user" else (character_name or "对话")
            lines.append(f"{label}: {content}")
    conv_text = "\n".join(lines)
    if len(conv_text) < 10:
        return {"facts_stored": 0}
    stored = extract_facts(conv_text, llm_adapter, character_id=character_id, store=store)
    return {"facts_stored": len(stored)}


def run_extraction_pipeline(
    llm_adapter: Any,
    character_name: str = "",
    character_id: str = "",
    store: Any = None,
) -> dict:
    """Run one full extraction cycle: summary → facts (per character)."""
    store = store or memory_store
    stats = {"summary": "", "facts_stored": 0}

    from app.memory.compiler import get_conversation_summary_record
    previous = get_conversation_summary_record(character_id)
    summary, through_log_id = run_rolling_summary(
        llm_adapter,
        character_name,
        character_id=character_id,
        store=store,
        return_record=True,
    )
    if not summary:
        return stats

    # B1: the full summary is persisted as the rolling conversation summary;
    # no longer truncated to 100 chars (that was only a boolean gate before).
    stats["summary"] = summary
    stats["through_log_id"] = through_log_id
    if (
        previous.get("content") == summary
        and int(previous.get("through_log_id", 0)) == int(through_log_id)
    ):
        stats["summary_unchanged"] = True
        return stats
    facts = extract_facts(
        summary, llm_adapter, character_id=character_id, store=store
    )
    stats["facts_stored"] = len(facts)

    return stats
