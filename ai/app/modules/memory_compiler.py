"""Memory Compiler — inspired by HanaAgent v3 memory architecture.

Reads from existing stores (memory.db, long_term.jsonl, memory.jsonl)
and compiles them into the 4-section memory.md format that the LLM
reads as context.

Pipeline:
  1. collect_recent_sessions()  — logs from last 24h (memory.db)
  2. collect_facts()            — facts from memory.db
  3. collect_longterm()         — recent + high-importance entries from long_term.jsonl
  4. compile_today()            — LLM compresses today's sessions → today.md
  5. compile_facts()            — LLM merges old + new facts → facts.md
  6. compile_longterm()         — LLM folds week entries → longterm.md
  7. assemble()                 — concatenates all 4 → memory.md (no LLM)
"""

import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("memory-compiler")

# Default paths relative to project root
_BASE_DIR = Path(__file__).resolve().parent.parent.parent

_PROMPTS: dict[str, dict[str, str]] = {
    "en": {
        "today_system": (
            "You are a memory compiler. Compress today's conversation logs into a concise summary of the user's current status and topics.\n\n"
            "Rules:\n"
            "- Merge multiple rounds on the same topic into one item — no line-by-line log\n"
            "- Prioritize: who the user is, what they like, what they care about, what they're focused on recently\n"
            "- Keep work content at the broad topic level only — no implementation details\n"
            "- Output 2-5 items, 1-2 sentences each. Max 200 words total\n"
            "- If nothing noteworthy today, output 'No significant conversations today'\n"
            "- Do NOT output Markdown headers — no #, ##, etc."
        ),
        "today_empty": "No significant conversations today",
        "facts_system": (
            "You are a fact compiler. Organize the following facts about the user into concise bullet points.\n\n"
            "Rules:\n"
            "- Merge duplicate or similar facts\n"
            "- Keep only the most important and relevant information\n"
            "- Output 3-10 items, one per line\n"
            "- If the list is empty, output 'No important facts recorded'"
        ),
        "facts_empty": "No important facts recorded",
        "longterm_system": (
            "You are a long-term memory compiler. Organize the following memory entries into a coherent summary of the user's long-term situation.\n\n"
            "Rules:\n"
            "- Merge multiple records on the same topic\n"
            "- Keep only stable, important information (personality traits, long-term interests, significant events)\n"
            "- Output 2-6 items, 1-2 sentences each. Max 300 words total\n"
            "- If the list is empty, output 'No long-term records'\n"
            "- Do NOT output Markdown headers"
        ),
        "longterm_empty": "No long-term records",
        "section_facts": "Important Facts",
        "section_today": "Today",
        "section_week": "Earlier This Week",
        "section_longterm": "Long-term",
    },
    "zh": {
        "today_system": (
            "你是一个记忆编译器。将今天的对话日志压缩成一份简洁的「用户近况与主题清单」。\n\n"
            "原则：\n"
            "- 把同一主题的多次往返归并为一条，不要逐条流水账\n"
            "- 优先记录用户是谁、喜欢什么、在意什么、最近关注什么\n"
            "- 工作内容只保留到大主题层级，不写细节\n"
            "- 输出 2-5 条，每条 1-2 句。最多 200 字\n"
            "- 如果今天没有值得记录的对话，输出「今天暂无重要对话」\n"
            "- 不要输出 Markdown 标题，不要以 #、## 开头"
        ),
        "today_empty": "今天暂无重要对话",
        "facts_system": (
            "你是一个事实编译器。将以下关于用户的事实列表整理成简洁的要点。\n\n"
            "原则：\n"
            "- 合并重复或相似的事实\n"
            "- 保留最重要、最相关的信息\n"
            "- 输出 3-10 条，每条一行\n"
            "- 如果列表为空，输出「暂无记录的重要事实」"
        ),
        "facts_empty": "暂无记录的重要事实",
        "longterm_system": (
            "你是一个长期记忆编译器。将以下长期记忆条目整理成一份连贯的「用户长期情况」。\n\n"
            "原则：\n"
            "- 合并同一主题的多条记录\n"
            "- 只保留重要且稳定的信息（人格特质、长期兴趣、重大事件）\n"
            "- 输出 2-6 条，每条 1-2 句。最多 300 字\n"
            "- 如果记录为空，输出「暂无长期记录」\n"
            "- 不要输出 Markdown 标题"
        ),
        "longterm_empty": "暂无长期记录",
        "section_facts": "重要事实",
        "section_today": "今天",
        "section_week": "本周早些时候",
        "section_longterm": "长期情况",
    },
}

# Language auto-detection from character card
_SUPPORTED_LANGS = {"en", "zh", "ja", "ko", "yue"}


def _get_char_lang(char_id: str) -> str:
    """Read character card to determine native language. Falls back to 'en'."""
    try:
        path = _BASE_DIR / "config" / "characters" / char_id / "character.json"
        if path.exists():
            import json
            card = json.loads(path.read_text("utf-8"))
            lang = card.get("reply_language") or card.get("tts", {}).get("prompt_lang", "en")
            if lang == "yue":
                lang = "zh"  # Written Cantonese uses the Chinese memory prompt family.
            return lang if lang in _PROMPTS else "en"
    except Exception:
        pass
    return "en"

# How many seconds old a "recent" session can be for today's compile
TODAY_HOURS = 24
# Long-term window: entries from last N days
LONGTERM_DAYS = 14
# Max tokens for compiled memory.md
MAX_MEMORY_TOKENS = 2000


# ═══════════════════════════════════════════════
#  Data collection
# ═══════════════════════════════════════════════

def _db_path() -> Path:
    return _BASE_DIR / "data" / "memory" / "memory.db"


def _longterm_path() -> Path:
    return _BASE_DIR / "data" / "memory" / "long_term.jsonl"


def _memory_jsonl_path() -> Path:
    return _BASE_DIR / "data" / "memory" / "memory.jsonl"


def _compiled_dir(char_id: str = "monika") -> Path:
    return _BASE_DIR / "data" / "memory" / "compiled" / char_id


def _collect_recent_sessions(hours: int = TODAY_HOURS) -> list[dict[str, Any]]:
    """Read recent conversation logs from memory.db (logs table)."""
    db = _db_path()
    if not db.exists():
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    try:
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT role, content, intent, created_at FROM logs WHERE created_at >= ? ORDER BY created_at ASC",
            (cutoff,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("collect_sessions failed: %s", exc)
        return []


def _collect_facts() -> list[dict[str, Any]]:
    """Read facts from memory.db (facts table), ordered by importance desc."""
    db = _db_path()
    if not db.exists():
        return []
    try:
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT fact, tags, importance, created_at FROM facts ORDER BY importance DESC LIMIT 50",
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("collect_facts failed: %s", exc)
        return []


def _collect_longterm(days: int = LONGTERM_DAYS) -> list[dict[str, Any]]:
    """Read recent + high-importance entries from long_term.jsonl."""
    path = _longterm_path()
    if not path.exists():
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    entries = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    created = entry.get("created_at", "")
                    importance = entry.get("importance", 0.5)
                    # Keep: recent entries OR high-importance entries
                    if (created and created >= cutoff) or (isinstance(importance, (int, float)) and importance >= 0.7):
                        entries.append(entry)
                except json.JSONDecodeError:
                    continue
        return entries
    except Exception as exc:
        logger.warning("collect_longterm failed: %s", exc)
        return []


def _collect_recent_conversations(hours: int = TODAY_HOURS) -> list[dict[str, str]]:
    """Read recent raw conversations from memory.jsonl as fallback for today's compile."""
    path = _memory_jsonl_path()
    if not path.exists():
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp()
    conversations = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    # Handle both formats
                    user_text = entry.get("user", "")
                    if not user_text:
                        user_text = entry.get("event", {}).get("transcript", "")
                    assistant_text = entry.get("assistant", "")
                    if not assistant_text:
                        assistant_text = entry.get("reply", {}).get("text", "")
                    created = entry.get("created_at", "")
                    if user_text and assistant_text:
                        conversations.append({
                            "user": user_text,
                            "assistant": assistant_text,
                            "created_at": created,
                        })
                except json.JSONDecodeError:
                    continue
        return conversations
    except Exception as exc:
        logger.warning("collect_conversations failed: %s", exc)
        return []


# ═══════════════════════════════════════════════
#  Fingerprint cache
# ═══════════════════════════════════════════════

def _compute_fingerprint(*data_parts: list) -> str:
    """Compute MD5 fingerprint from multiple data sources."""
    raw = "|".join(str(p) for p in data_parts if p)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _read_fingerprint(path: Path) -> str:
    try:
        return path.read_text("utf-8").strip()
    except Exception:
        return ""


def _write_fingerprint(path: Path, fp: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fp, encoding="utf-8")


# ═══════════════════════════════════════════════
#  LLM compilation
# ═══════════════════════════════════════════════

def _call_llm(system_prompt: str, user_text: str, max_tokens: int = 600) -> str:
    """Call DeepSeek via OpenAILLMAdapter with plain text output."""
    try:
        from app.models.http_adapters import OpenAILLMAdapter
        adapter = OpenAILLMAdapter()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]
        result = adapter.generate(
            messages,
            temperature=0.3,
            response_format=None,
            max_tokens=max_tokens,
        )
        return str(result.get("content", "")).strip()
    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        return ""


def _compile_today(sessions: list[dict], conversations: list[dict], lang: str = "en") -> str:
    """LLM compresses today's logs into a concise summary."""
    if not sessions and not conversations:
        return ""

    prompts = _PROMPTS.get(lang, _PROMPTS["en"])

    # Build input text from sessions and conversations
    lines = []
    for s in sessions:
        role = s.get("role", "?")
        content = s.get("content", "")
        if content:
            lines.append(f"[{role}] {content[:200]}")

    for c in conversations:
        user_t = c.get("user", "")[:200]
        asst_t = c.get("assistant", "")[:200]
        if user_t:
            lines.append(f"[user] {user_t}")
        if asst_t:
            lines.append(f"[assistant] {asst_t}")

    input_text = "\n".join(lines)
    if not input_text.strip():
        return prompts["today_empty"]

    return _call_llm(prompts["today_system"], input_text, max_tokens=400)


def _compile_facts(fact_rows: list[dict], lang: str = "en") -> str:
    """Compile facts into a concise list."""
    prompts = _PROMPTS.get(lang, _PROMPTS["en"])

    if not fact_rows:
        return prompts["facts_empty"]

    lines = []
    for f in fact_rows:
        fact = f.get("fact", "")
        tags = f.get("tags", "[]")
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                tags = []
        tag_str = ", ".join(tags[:3]) if tags else ""
        if fact:
            lines.append(f"- {fact}" + (f"  [{tag_str}]" if tag_str else ""))

    input_text = "\n".join(lines)
    if not input_text.strip():
        return prompts["facts_empty"]

    return _call_llm(prompts["facts_system"], input_text, max_tokens=300)


def _compile_longterm(entries: list[dict], lang: str = "en") -> str:
    """LLM folds long-term entries into a coherent summary."""
    prompts = _PROMPTS.get(lang, _PROMPTS["en"])

    if not entries:
        return prompts["longterm_empty"]

    lines = []
    for e in entries:
        content = e.get("content", "")
        etype = e.get("type", "note")
        if content:
            lines.append(f"[{etype}] {content[:300]}")

    input_text = "\n".join(lines)
    if not input_text.strip():
        return prompts["longterm_empty"]

    return _call_llm(prompts["longterm_system"], input_text, max_tokens=500)


# ═══════════════════════════════════════════════
#  Assemble
# ═══════════════════════════════════════════════

def _assemble(memory_dir: Path, lang: str = "en") -> None:
    """Read 4 intermediate files and assemble into memory.md."""
    prompts = _PROMPTS.get(lang, _PROMPTS["en"])

    today_path = memory_dir / "today.md"
    week_path = memory_dir / "week.md"
    longterm_path = memory_dir / "longterm.md"
    facts_path = memory_dir / "facts.md"
    memory_md_path = memory_dir / "memory.md"

    def read_section(path: Path) -> str:
        try:
            return path.read_text("utf-8").strip()
        except Exception:
            return ""

    today = read_section(today_path)
    week = read_section(week_path)
    longterm = read_section(longterm_path)
    facts = read_section(facts_path)

    # Build markdown with default placeholders for empty sections
    def section(title: str, body: str, placeholder: str) -> str:
        return f"## {title}\n\n{body if body else placeholder}"

    placeholder = "(empty)" if lang == "en" else "（暂无）"
    content = "\n\n".join([
        section(prompts["section_facts"], facts, placeholder),
        section(prompts["section_today"], today, placeholder),
        section(prompts["section_week"], week, placeholder),
        section(prompts["section_longterm"], longterm, placeholder),
    ]) + "\n"

    # Truncate to approximate token limit (4 chars ≈ 1 token for Chinese/English mix)
    if len(content) > MAX_MEMORY_TOKENS * 4:
        content = content[: MAX_MEMORY_TOKENS * 4]
        # Try to break at a section boundary
        last_section = max(
            content.rfind(f"\n## {prompts['section_facts']}"),
            content.rfind(f"\n## {prompts['section_today']}"),
            content.rfind(f"\n## {prompts['section_week']}"),
            content.rfind(f"\n## {prompts['section_longterm']}"),
        )
        if last_section > 0:
            content = content[:last_section] + "\n"

    memory_md_path.parent.mkdir(parents=True, exist_ok=True)
    # Force UTF-8 (Windows defaults to GBK)
    memory_md_path.write_text(content, encoding="utf-8")
    logger.info("[Compile] Assembled memory.md (%d chars)", len(content))


# ═══════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════

def compile(char_id: str = "monika", lang: str | None = None) -> bool:
    """Run the full memory compilation pipeline.

    Args:
        char_id: Character ID (directory name in config/characters/).
        lang: Language code ('en', 'zh', etc.). Auto-detected from character card if None.

    Returns True if memory.md was updated, False if nothing changed (cached).
    """
    memory_dir = _compiled_dir(char_id)
    memory_dir.mkdir(parents=True, exist_ok=True)

    # Auto-detect language from character card
    if lang is None:
        lang = _get_char_lang(char_id)
    lang = lang if lang in _PROMPTS else "en"

    # Collect data
    sessions = _collect_recent_sessions()
    facts = _collect_facts()
    longterm = _collect_longterm()
    conversations = _collect_recent_conversations()

    # Compute fingerprint to skip if nothing changed
    fp = _compute_fingerprint(sessions, facts, longterm, conversations, lang)
    fp_path = memory_dir / ".compile.fingerprint"
    if _read_fingerprint(fp_path) == fp:
        logger.info("[Compile] Skipped (fingerprint unchanged)")
        return False

    logger.info("[Compile] Starting (lang=%s, %d sessions, %d facts, %d longterm, %d convos)",
                lang, len(sessions), len(facts), len(longterm), len(conversations))

    # Compile sections (each returns empty string on failure, which is fine)
    today_result = _compile_today(sessions, conversations, lang)
    (memory_dir / "today.md").write_text(today_result, encoding="utf-8")
    logger.info("[Compile] today.md: %d chars", len(today_result))

    facts_result = _compile_facts(facts, lang)
    (memory_dir / "facts.md").write_text(facts_result, encoding="utf-8")
    logger.info("[Compile] facts.md: %d chars", len(facts_result))

    longterm_result = _compile_longterm(longterm, lang)
    (memory_dir / "longterm.md").write_text(longterm_result, encoding="utf-8")
    logger.info("[Compile] longterm.md: %d chars", len(longterm_result))

    # Assemble final memory.md
    _assemble(memory_dir, lang)
    _write_fingerprint(fp_path, fp)
    logger.info("[Compile] Done")
    return True
