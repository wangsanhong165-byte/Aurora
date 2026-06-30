"""Memory compiler — four-section compilation pipeline.

Sections (same as openhanako v3):
  - today:    current day summary (3-5 coarse events, ≤300 chars)
  - week:     past 7-day sliding window (broad themes)
  - longterm: folded long-term context (≤600 tokens)
  - facts:    stable user profile (≤300 tokens)

Assembles into memory.md (≤2000 tokens) for PromptBuilder to read.

Plan B design:
- Facts (shared): stored in global SQLite, character-independent
- Compiled memory (per-character): stored in memory/compiled/{char_id}/
- On character switch: regenerate compiled memory from shared facts
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Optional

from app.memory.store import memory_store
from app.memory.prompts import (
    system_compile_today,
    system_compile_week,
    system_compile_longterm,
    system_compile_facts,
)

_BASE_DIR: Optional[Path] = None
_llm_adapter_global: Any = None
_current_char_id: str = ""
_on_switch_callbacks: list = []


def _get_base() -> Path:
    global _BASE_DIR
    if _BASE_DIR is None:
        _BASE_DIR = Path(__file__).resolve().parents[2]
    return _BASE_DIR


def _char_dir(char_id: str) -> Path:
    """Per-character compiled directory."""
    d = _get_base() / "data" / "memory" / "compiled" / (char_id or "default")
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_compiled_memory(char_id: str = "") -> str:
    """Read assembled memory.md for given character. Falls back to current."""
    cid = char_id or _current_char_id or "default"
    path = _char_dir(cid) / "memory.md"
    if path.exists():
        return path.read_text("utf-8").strip()
    return ""


# ── helpers ──────────────────────────────────────────────────────────

def _fingerprint(content: str) -> str:
    return hashlib.md5(content.encode()).hexdigest()


def _check_cache(char_id: str, name: str, data: str) -> bool:
    dirpath = _char_dir(char_id)
    fp_path = dirpath / f"{name}.fp"
    md_path = dirpath / f"{name}.md"
    fp = _fingerprint(data)
    if fp_path.exists() and md_path.exists():
        try:
            return fp_path.read_text("utf-8").strip() == fp
        except OSError:
            return False
    return False


def _write_cache(char_id: str, name: str, data: str, content: str):
    dirpath = _char_dir(char_id)
    fp = _fingerprint(data)
    (dirpath / f"{name}.fp").write_text(fp, "utf-8")
    (dirpath / f"{name}.md").write_text(content, "utf-8")


def _read_section(char_id: str, name: str) -> str:
    path = _char_dir(char_id) / f"{name}.md"
    if path.exists():
        return path.read_text("utf-8").strip()
    return ""


def _char_name_from_id(char_id: str) -> str:
    """Read character display name from its character.json."""
    try:
        path = _get_base() / "characters" / char_id / "character.json"
        if path.exists():
            import json
            card = json.loads(path.read_text("utf-8"))
            name = card.get("name", {})
            return name.get("zh", name.get("ja", char_id))
    except Exception:
        pass
    return char_id


def _call_llm(system: str, user: str, timeout: int = 15) -> str:
    global _llm_adapter_global
    if not _llm_adapter_global:
        return ""
    return _llm_adapter_global.generate_text(
        system=system,
        user=user,
        temperature=0.3,
        max_tokens=1024,
        timeout=timeout,
    )


def set_llm_adapter(adapter: Any):
    global _llm_adapter_global
    _llm_adapter_global = adapter


def get_active_char_id() -> str:
    return _current_char_id or "default"


def set_active_char(char_id: str):
    """Set active character. Does NOT trigger compilation (caller decides)."""
    global _current_char_id
    _current_char_id = char_id


# ── compilation functions ────────────────────────────────────────────

def today_digest(char_id: str = "") -> str:
    """Compile today's log into a brief summary for given character."""
    cid = char_id or _current_char_id or "default"
    char_name = _char_name_from_id(cid)

    today_start = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()[:10]
    turns = memory_store.recent_turns(50)
    if not turns:
        return ""

    today_turns = [t for t in turns if str(t.get("created_at", "")).startswith(today_start)]
    if not today_turns:
        return ""

    lines = []
    for t in today_turns:
        role = t.get("role", "")
        content = str(t.get("content", "")).strip()
        if content:
            label = "用户" if role == "user" else (char_name or "AI")
            lines.append(f"{label}: {content}")
    text = "\n".join(lines)

    if _check_cache(cid, "today", text):
        return _read_section(cid, "today")

    result = _call_llm(system_compile_today(char_name), text)
    if result:
        _write_cache(cid, "today", text, result)
    return result or ""


def week_digest(char_id: str = "") -> str:
    """Compile past week's context for given character."""
    cid = char_id or _current_char_id or "default"
    char_name = _char_name_from_id(cid)
    existing_week = _read_section(cid, "week")

    turns = memory_store.recent_turns(200)
    if not turns:
        return ""

    parts = []
    if existing_week:
        parts.append(f"[已有本周记录]\n{existing_week}")
    lines = []
    for t in turns[-100:]:
        role = t.get("role", "")
        content = str(t.get("content", "")).strip()
        if content:
            label = "用户" if role == "user" else (char_name or "AI")
            lines.append(f"{label}: {content}")
    if lines:
        parts.append("[最近对话]\n" + "\n".join(lines))
    text = "\n\n".join(parts)

    if _check_cache(cid, "week", text):
        return _read_section(cid, "week")

    result = _call_llm(system_compile_week(char_name), text, timeout=20)
    if result:
        _write_cache(cid, "week", text, result)
    return result or ""


def longterm_digest(char_id: str = "", week_summary: str = "") -> str:
    """Fold existing long-term context with weekly summary for given character."""
    cid = char_id or _current_char_id or "default"
    existing_longterm = _read_section(cid, "longterm")

    parts = []
    if existing_longterm:
        parts.append(f"[已有长期上下文]\n{existing_longterm}")
    if week_summary:
        parts.append(f"[本周概要]\n{week_summary}")
    if not parts:
        return ""

    text = "\n\n".join(parts)

    if _check_cache(cid, "longterm", text):
        return _read_section(cid, "longterm")

    result = _call_llm(system_compile_longterm(), text, timeout=20)
    if result:
        _write_cache(cid, "longterm", text, result)
    return result or ""


def facts_digest(char_id: str = "") -> str:
    """Compile all stored facts into a stable user profile summary."""
    cid = char_id or _current_char_id or "default"

    facts = memory_store.get_all_facts()
    if not facts:
        return ""

    lines = [f"- {f['fact']}" for f in facts[:30]]
    text = "\n".join(lines)

    if _check_cache(cid, "facts", text):
        return _read_section(cid, "facts")

    result = _call_llm(system_compile_facts(), text, timeout=20)
    if result:
        _write_cache(cid, "facts", text, result)
    return result or ""


def assemble(char_id: str = ""):
    """Read all four sections for given character and write memory.md."""
    cid = char_id or _current_char_id or "default"

    today = _read_section(cid, "today") or "（暂无）"
    week = _read_section(cid, "week") or "（暂无）"
    longterm = _read_section(cid, "longterm") or "（暂无）"
    facts = _read_section(cid, "facts") or "（暂无）"

    content = (
        "## 重要事实\n\n" + facts +
        "\n\n## 今天\n\n" + today +
        "\n\n## 本周早些时候\n\n" + week +
        "\n\n## 长期情况\n\n" + longterm + "\n"
    )
    path = _char_dir(cid) / "memory.md"
    path.write_text(content, "utf-8")


def compile_and_assemble(char_id: str = ""):
    """Run all four compilations then assemble. Call once per day."""
    cid = char_id or _current_char_id or "default"

    existing_longterm = _read_section(cid, "longterm")
    existing_week = _read_section(cid, "week")

    new_week = week_digest(cid)
    new_longterm = longterm_digest(cid, new_week)
    new_facts = facts_digest(cid)
    today = today_digest(cid)

    assemble(cid)


def compile_today_and_assemble(char_id: str = ""):
    """Compile today's digest then assemble. Call after rolling summary."""
    cid = char_id or _current_char_id or "default"
    today = today_digest(cid)
    if today:
        assemble(cid)
    return today


# ── character switch support ─────────────────────────────────────────

def regenerate_for_character(char_id: str):
    """Regenerate all compiled memory for a target character from shared facts.
    
    Called when switching personas. Does NOT re-extract facts (they're shared).
    Re-compiles today/week/longterm/facts from the shared fact store.
    """
    char_name = _char_name_from_id(char_id)
    print(f"[compiler] Regenerating memory for character: {char_name} ({char_id})")

    # Compile facts section from shared facts
    facts = memory_store.get_all_facts()
    if facts:
        text = "\n".join(f"- {f['fact']}" for f in facts[:30])
        result = _call_llm(system_compile_facts(), text, timeout=20)
        if result:
            _write_cache(char_id, "facts", text, result)

    # Compile today from shared log
    today = today_digest(char_id)

    # Assemble
    assemble(char_id)
    print(f"[compiler] Memory regenerated for {char_name}")
    return True


def register_switch_callback(callback):
    _on_switch_callbacks.append(callback)
