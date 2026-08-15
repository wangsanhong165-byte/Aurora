"""LLM-based merge of near-duplicate memories for one character.

Runs on a daily/threshold cadence, off the voice loop, only when a character
has enough active memories that fragmentation is plausible. Design constraints:

- Never hard-deletes: merged-away memories are soft-deleted (active=0), the
  same reversible lifecycle the decay uses. If the same content is re-extracted
  later, upsert revives it — that is a re-confirmation, not a bug.
- Reconciliation (Hermes curator pattern): if the merge target vanished or its
  stable_key changed while the LLM call was in flight, the whole group is
  abandoned rather than fabricating a target (protects against LLM hallucination
  and concurrent writes from the reviewer/extractor).
- Candidate selection uses list_memories (pure read) — never search_memories,
  which would bump access_count/last_retrieved_at and pollute the familiarity
  signal.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger("memory.merger")

_MIN_GROUP_SIZE = 2
_MAX_GROUPS = 3
_MIN_MEMORIES_TO_MERGE = 80


def _call_llm(system: str, user: str, llm_adapter: Any, timeout: int = 20) -> str:
    if not llm_adapter:
        return ""
    return llm_adapter.generate_text(
        system=system,
        user=user,
        temperature=0.3,
        max_tokens=512,
        timeout=timeout,
    )


def _group_candidates(store: Any, character_id: str) -> list[list[dict]]:
    """Group active memories by predicate; return groups with >= 2 members."""
    memories = store.list_memories(
        character_id=character_id, active_only=True, limit=500
    )
    by_predicate: dict[str, list[dict]] = {}
    for m in memories:
        by_predicate.setdefault(str(m.get("predicate") or "other"), []).append(m)
    return [
        group for group in by_predicate.values()
        if len(group) >= _MIN_GROUP_SIZE
    ]


def _merge_prompt(group: list[dict]) -> str:
    lines = []
    for m in group:
        lines.append(
            f"- id={m['id']} content={m['content']!r} "
            f"(importance={m.get('importance', 0.5)}, "
            f"confidence={m.get('confidence', 0.6)}, "
            f"updated={str(m.get('updated_at', ''))[:10]})"
        )
    return (
        "You are merging near-duplicate memory entries. The following memories "
        "share a predicate (the same stable attribute of the user) and are "
        "candidates for collapse into one fact.\n\n"
        + "\n".join(lines) + "\n\n"
        "Output JSON only: {\"merge_into\": <target id>, \"obsolete\": [<ids>], "
        "\"new_content\": \"<merged text>\", \"importance\": 0.8}\n"
        "Rules:\n"
        "- merge_into must be one of the given ids — pick the richest memory.\n"
        "- new_content: one coherent Chinese fact, 5-120 chars, merging the "
        "essential information and dropping redundancies.\n"
        "- obsolete: the OTHER ids fully absorbed by the merge (may be empty).\n"
        "- importance: 0-1 reflecting how important the merged fact is.\n"
        "- If the memories are genuinely distinct and must NOT be merged, "
        "return {\"merge_into\": null}."
    )


def _parse_merge_result(text: str) -> dict | None:
    if not text:
        return None
    text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except (json.JSONDecodeError, TypeError):
            return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def merge_memories(
    llm_adapter: Any,
    store: Any,
    character_id: str = "",
    max_groups: int = _MAX_GROUPS,
) -> dict:
    """Merge near-duplicate memories for one character. Returns stats dict."""
    stats = {"groups_considered": 0, "merged": 0, "obsolete": 0, "skipped": 0}
    if not llm_adapter or not character_id:
        return stats
    memories = store.list_memories(
        character_id=character_id, active_only=True, limit=500
    )
    if len(memories) < _MIN_MEMORIES_TO_MERGE:
        stats["skipped"] = len(memories)
        return stats
    for group in _group_candidates(store, character_id)[:max_groups]:
        stats["groups_considered"] += 1
        parsed = _parse_merge_result(
            _call_llm(
                "You are a memory consolidation assistant.",
                _merge_prompt(group),
                llm_adapter,
            )
        )
        target_id = parsed.get("merge_into") if parsed else None
        new_content = str(parsed.get("new_content", "")).strip() if parsed else ""
        if (
            target_id is None
            or not new_content
            or len(new_content) < 5
            or len(new_content) > 120
        ):
            stats["skipped"] += 1
            continue
        try:
            target_id = int(target_id)
        except (TypeError, ValueError):
            stats["skipped"] += 1
            continue
        # Reconciliation: the target must still exist and be active.
        target = store._get_conn().execute(
            "SELECT memory_type, subject, predicate, stable_key "
            "FROM memories WHERE id = ? AND active = 1",
            (target_id,),
        ).fetchone()
        if target is None:
            stats["skipped"] += 1
            continue
        # Apply the merged content under the target's identity (upsert handles
        # the UNIQUE(character_id, stable_key, content) constraint by
        # soft-deleting the old row when the content changes).
        store.upsert_memory(
            memory_type=str(target["memory_type"]),
            subject=str(target["subject"]),
            predicate=str(target["predicate"]),
            content=new_content,
            character_id=character_id,
            importance=float(parsed.get("importance", 0.7) or 0.7),
            confidence=0.8,
            stable_key=str(target["stable_key"]),
        )
        stats["merged"] += 1
        for raw in parsed.get("obsolete", []) or []:
            try:
                obsolete_id = int(raw)
            except (TypeError, ValueError):
                continue
            if obsolete_id == target_id:
                continue
            if store.forget_memory(obsolete_id, character_id=character_id):
                stats["obsolete"] += 1
    return stats
