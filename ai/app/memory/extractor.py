"""Memory extractor — rolling summary + fact extraction.

Background pipeline. Character-agnostic: accepts character_name parameter
so the same pipeline works for any persona.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.memory.store import memory_store
from app.memory.prompts import (
    system_rolling_summary,
    system_fact_extraction,
)

_TURNS_PER_SUMMARY = 10
_RECENT_PROMPT_MESSAGES = 10

# Deterministic open_loop extraction from the rolling summary's "[还悬着]" section.
_PENDING_SECTION = "[还悬着]"
_NEXT_SECTION_MARKERS = ("[现状]", "[已聊透]")
_OPEN_LOOP_PREDICATE = "pending_topic"
_EMPTY_PENDING_MARKERS = ("（无）", "(无)", "无", "none")


def _parse_pending_section(summary: str) -> list[str]:
    """Parse pending-topic items out of the summary's [还悬着] section.

    No LLM: the summarizer is already instructed to write 1-3 short pending
    lines under that header, so this just splits them deterministically.
    Returns at most 3 normalized items.
    """
    if not summary:
        return []
    start = summary.find(_PENDING_SECTION)
    if start == -1:
        return []
    body = summary[start + len(_PENDING_SECTION):]
    for marker in _NEXT_SECTION_MARKERS:
        idx = body.find(marker)
        if idx != -1:
            body = body[:idx]
            break
    body = body.strip()
    if not body or body.strip().strip("：:") in _EMPTY_PENDING_MARKERS:
        return []
    items: list[str] = []
    for chunk in re.split(r"[\n；;。！!？?]+", body):
        chunk = chunk.strip().lstrip("-*·• ")
        if chunk and len(chunk) >= 4:
            items.append(chunk)
    return items[:3]


def _pending_topic_key(content: str) -> str:
    """Stable dedup key for a pending topic (word-normalized content)."""
    normalized = re.sub(r"[\W_]+", "", content.lower())
    return normalized[:40] or "topic"


def sync_open_loops(store: Any, character_id: str, summary: str) -> dict:
    """Persist pending threads as open_loop memories; close ones that resolved.

    Runs only when the rolling summary actually changed, so a stale summary
    never resurrects closed loops. Closing is a soft delete (active=0), the
    same reversible lifecycle the decay uses — a reopened topic is revived by
    the next upsert instead of being re-created.
    """
    stats = {"open_loops_open": 0, "open_loops_closed": 0}
    if not character_id:
        return stats
    pending = _parse_pending_section(summary)
    for item in pending:
        store.upsert_memory(
            memory_type="open_loop",
            subject="user",
            predicate=_OPEN_LOOP_PREDICATE,
            content=item,
            character_id=character_id,
            importance=0.7,
            confidence=0.8,
            stable_key=f"open_loop:user:{_OPEN_LOOP_PREDICATE}:{_pending_topic_key(item)}",
        )
        stats["open_loops_open"] += 1
    # Close loops that are no longer pending in the current summary.
    current = store.list_memories(
        character_id=character_id, memory_type="open_loop",
        active_only=True, limit=100,
    )
    pending_texts = {item for item in pending}
    for mem in current:
        content = str(mem.get("content", "")).strip()
        if content and content not in pending_texts:
            store.forget_memory(mem["id"], character_id=character_id)
            stats["open_loops_closed"] += 1
    return stats


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
    stats["open_loops"] = sync_open_loops(store, character_id, summary)

    return stats
