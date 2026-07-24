"""Memory store — SQLite + FTS5 backend.

Replaces JSONL with structured storage.

Facts table: id, fact, tags (JSON), time, source, importance, created_at
Logs table:  id, role, content, intent, created_at
Both backed by FTS5 virtual tables for full-text search.

Search strategy (two-tier, same as openhanako v2):
  1. Tag exact match via json_each (OR logic, sorted by match count)
  2. FTS5 full-text fallback (with CJK bigram)
  3. LIKE fallback if FTS5 fails
"""

from __future__ import annotations

import json
import sqlite3
import threading
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+")
_FTS_LIMIT = 20


def _cjk_ngrams(text: str, sizes=(2, 3)) -> list[str]:
    """Generate CJK bigrams/trigrams for FTS5 tokenization."""
    tokens = []
    for match in _CJK_RE.finditer(text):
        chars = list(match.group(0))
        for size in sizes:
            if len(chars) < size:
                continue
            for i in range(len(chars) - size + 1):
                tokens.append("".join(chars[i:i + size]))
    return tokens


def _build_fts_query(text: str) -> str:
    """Build FTS5 query: lexical tokens + CJK ngrams joined by OR."""
    normalized = text.strip().lower()
    if not normalized:
        return ""
    lexical = normalized.split()
    grams = _cjk_ngrams(normalized)
    all_tokens = list(dict.fromkeys(lexical + grams))
    return " OR ".join(f'"{w}"' for w in all_tokens if w)


class MemoryStore:
    """SQLite+FTS5 memory store. Drop-in replacement for JSONL-based store."""

    def __init__(self, base_dir: Optional[Path] = None):
        base = base_dir or Path(__file__).resolve().parents[2]
        base.mkdir(parents=True, exist_ok=True)
        db_path = base / "data" / "memory" / "memory.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = str(db_path)
        self._local = threading.local()
        self._init_db()

    # ── connection management ──────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA cache_size = -16000")
            conn.execute("PRAGMA temp_store = MEMORY")
            conn.execute("PRAGMA mmap_size = 30000000")
            self._local.conn = conn
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS facts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                fact       TEXT NOT NULL,
                tags       TEXT NOT NULL DEFAULT '[]',
                time       TEXT,
                source     TEXT DEFAULT '',
                importance REAL DEFAULT 0.5,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_facts_time ON facts(time);
            CREATE INDEX IF NOT EXISTS idx_facts_importance ON facts(importance);

            CREATE TABLE IF NOT EXISTS logs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                role       TEXT NOT NULL,
                content    TEXT NOT NULL,
                intent     TEXT DEFAULT '',
                character_id TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_logs_created ON logs(created_at);

            CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
                fact, tags,
                content=facts, content_rowid=id,
                tokenize='unicode61'
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS logs_fts USING fts5(
                content,
                content=logs, content_rowid=id,
                tokenize='unicode61'
            );
        """)
        conn.executescript("""
            CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
                INSERT INTO facts_fts(rowid, fact, tags) VALUES (new.id, new.fact, new.tags);
            END;
            CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
                INSERT INTO facts_fts(facts_fts, rowid, fact, tags) VALUES ('delete', old.id, old.fact, old.tags);
            END;
            CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
                INSERT INTO facts_fts(facts_fts, rowid, fact, tags) VALUES ('delete', old.id, old.fact, old.tags);
                INSERT INTO facts_fts(rowid, fact, tags) VALUES (new.id, new.fact, new.tags);
            END;
            CREATE TRIGGER IF NOT EXISTS logs_ai AFTER INSERT ON logs BEGIN
                INSERT INTO logs_fts(rowid, content) VALUES (new.id, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS logs_ad AFTER DELETE ON logs BEGIN
                INSERT INTO logs_fts(logs_fts, rowid, content) VALUES ('delete', old.id, old.content);
            END;
        """)
        conn.commit()

    # ── conversation log ───────────────────────────────────────────────

    def log_turn(self, user_text: str, reply: dict, character_id: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        if user_text.strip():
            conn.execute(
                "INSERT INTO logs(role, content, intent, character_id, created_at) VALUES (?, ?, ?, ?, ?)",
                ("user", user_text[:1000], reply.get("intent", "unknown"), character_id, now),
            )
        reply_text = reply.get("reply_text", "")[:2000]
        if reply_text.strip():
            conn.execute(
                "INSERT INTO logs(role, content, intent, character_id, created_at) VALUES (?, ?, ?, ?, ?)",
                ("assistant", reply_text, reply.get("intent", "reply"), character_id, now),
            )
        conn.commit()

    def enqueue_turn(self, user_text: str, reply: dict) -> None:
        self.log_turn(user_text, reply)

    def recent_turns(self, n: int = 10) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT role, content, intent, created_at FROM logs ORDER BY id DESC LIMIT ?",
            (n * 2,),
        ).fetchall()
        turns = []
        for r in reversed(rows):
            turns.append({
                "role": r["role"],
                "content": r["content"],
                "intent": r["intent"],
                "created_at": r["created_at"],
            })
        return turns

    def search_logs(
        self, query: str, limit: int = 5, character_id: str = ""
    ) -> list[dict]:
        fts_query = _build_fts_query(query)
        if not fts_query:
            return []
        conn = self._get_conn()
        try:
            if character_id:
                rows = conn.execute(
                    "SELECT l.role, l.content, l.intent, l.character_id, l.created_at "
                    "FROM logs_fts f JOIN logs l ON f.rowid = l.id "
                    "WHERE logs_fts MATCH ? AND l.character_id = ? "
                    "ORDER BY rank LIMIT ?",
                    (fts_query, character_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT l.role, l.content, l.intent, l.character_id, l.created_at "
                    "FROM logs_fts f JOIN logs l ON f.rowid = l.id "
                    "WHERE logs_fts MATCH ? ORDER BY rank LIMIT ?",
                    (fts_query, limit),
                ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [dict(r) for r in rows]

    # ── facts ──────────────────────────────────────────────────────────

    def add_fact(
        self,
        content: str,
        tags: Optional[list[str]] = None,
        importance: float = 0.5,
        source: str = "",
        time: Optional[str] = None,
    ) -> bool:
        if not content or len(content.strip()) < 3:
            return False
        tags = tags or []
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        existing = self._find_overlapping(content, tags)
        if existing:
            return False
        conn.execute(
            "INSERT INTO facts(fact, tags, time, source, importance, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (content.strip(), json.dumps(tags, ensure_ascii=False), time, source, importance, now),
        )
        conn.commit()
        return True

    def _find_overlapping(self, content: str, tags: list[str]) -> bool:
        if not tags:
            return False
        conn = self._get_conn()
        placeholders = ",".join("?" for _ in tags)
        row = conn.execute(
            f"SELECT COUNT(DISTINCT je.value) as overlap FROM facts f, json_each(f.tags) je "
            f"WHERE je.value IN ({placeholders}) ORDER BY overlap DESC LIMIT 1",
            tags,
        ).fetchone()
        return row is not None and row["overlap"] > 0

    def search_facts(
        self,
        query: str = "",
        tags: Optional[list[str]] = None,
        k: int = 5,
    ) -> list[dict]:
        results = []
        seen_ids = set()
        conn = self._get_conn()

        # Strategy 1: tag matching
        if tags:
            placeholders = ",".join(f"@t{i}" for i in range(len(tags)))
            params = {f"t{i}": t for i, t in enumerate(tags)}
            params["limit"] = _FTS_LIMIT
            rows = conn.execute(
                f"SELECT f.*, COUNT(DISTINCT je.value) as match_count "
                f"FROM facts f, json_each(f.tags) je "
                f"WHERE je.value IN ({placeholders}) "
                f"GROUP BY f.id ORDER BY match_count DESC, f.importance DESC LIMIT @limit",
                params,
            ).fetchall()
            for r in rows:
                seen_ids.add(r["id"])
                results.append(self._row_to_fact(r))

        # Strategy 2: FTS5 fallback
        if len(results) < 3 and query:
            fts_query = _build_fts_query(query)
            if fts_query:
                try:
                    rows = conn.execute(
                        "SELECT f.* FROM facts_fts fts JOIN facts f ON fts.rowid = f.id "
                        "WHERE facts_fts MATCH ? ORDER BY rank LIMIT ?",
                        (fts_query, _FTS_LIMIT),
                    ).fetchall()
                    for r in rows:
                        if r["id"] in seen_ids:
                            continue
                        seen_ids.add(r["id"])
                        results.append(self._row_to_fact(r))
                except sqlite3.OperationalError:
                    pass

        # Strategy 3: LIKE fallback
        if len(results) < 3 and query:
            rows = conn.execute(
                "SELECT * FROM facts WHERE fact LIKE ? ORDER BY importance DESC LIMIT ?",
                (f"%{query}%", _FTS_LIMIT),
            ).fetchall()
            for r in rows:
                if r["id"] in seen_ids:
                    continue
                results.append(self._row_to_fact(r))

        return results[:k]

    def get_all_facts(self) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM facts ORDER BY importance DESC, created_at DESC").fetchall()
        return [self._row_to_fact(r) for r in rows]

    def delete_fact(self, fact_id: int) -> bool:
        conn = self._get_conn()
        return conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,)).rowcount > 0

    @property
    def fact_count(self) -> int:
        conn = self._get_conn()
        return conn.execute("SELECT COUNT(*) as c FROM facts").fetchone()["c"]

    def _row_to_fact(self, r) -> dict:
        tags_raw = r["tags"]
        if isinstance(tags_raw, str):
            try:
                tags = json.loads(tags_raw)
            except (json.JSONDecodeError, TypeError):
                tags = []
        else:
            tags = tags_raw or []
        return {
            "id": r["id"],
            "fact": r["fact"],
            "tags": tags,
            "time": r["time"] if r["time"] else None,
            "source": r["source"] if r["source"] else "",
            "importance": float(r["importance"]) if r["importance"] else 0.5,
            "created_at": r["created_at"] if r["created_at"] else "",
        }

    # ── prompt context (legacy compat, will be replaced by compiler) ────

    def build_prompt_context(self, query="", max_recent_turns=5, max_facts=3):
        sections = []
        turns = self.recent_turns(max_recent_turns)
        if turns:
            lines = ["\n[最近对话]"]
            for t in turns:
                content = str(t.get("content", "")).strip()
                role = t.get("role", "user")
                if content:
                    lines.append(f"{'用户' if role == 'user' else 'Monika'}: {content[:200]}")
            sections.append("\n".join(lines))

        facts = self.search_facts(query=query, k=max_facts)
        if facts:
            lines = ["\n[记忆]"]
            for f in facts:
                lines.append("  " + str(f.get("fact", "")))
            sections.append("\n".join(lines))

        return "\n".join(sections)

    def rebuild_index(self):
        conn = self._get_conn()
        conn.executescript("""
            INSERT INTO facts_fts(facts_fts) VALUES ('rebuild');
            INSERT INTO logs_fts(logs_fts) VALUES ('rebuild');
        """)
        return self.fact_count

    def delete_logs_before(self, cutoff: str) -> int:
        """Delete log entries older than cutoff (ISO datetime string). Returns count."""
        conn = self._get_conn()
        cur = conn.execute("DELETE FROM logs WHERE created_at < ?", (cutoff,))
        deleted = cur.rowcount
        conn.commit()
        return deleted

    def delete_facts_before(self, cutoff: str) -> int:
        """Delete facts older than cutoff (ISO datetime string). Returns count."""
        conn = self._get_conn()
        cur = conn.execute("DELETE FROM facts WHERE created_at < ?", (cutoff,))
        deleted = cur.rowcount
        conn.commit()
        return deleted

    def start(self):
        pass

    def stop(self, wait=False):
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


memory_store = MemoryStore()



