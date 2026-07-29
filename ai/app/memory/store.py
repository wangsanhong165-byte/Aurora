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
import shutil
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
        self._backup_before_v3()
        self._init_db()

    def _backup_before_v3(self) -> None:
        """Create one recoverable copy before the first V3 schema migration."""
        db_path = Path(self._db_path)
        backup_path = db_path.with_suffix(".v2-backup.db")
        if db_path.exists() and db_path.stat().st_size and not backup_path.exists():
            shutil.copy2(db_path, backup_path)

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
                character_id TEXT DEFAULT '',
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
                turn_id    TEXT,
                write_token TEXT,
                history_uid TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_logs_created ON logs(created_at);
            CREATE TABLE IF NOT EXISTS turn_commits (
                character_id TEXT NOT NULL,
                turn_id TEXT NOT NULL,
                write_token TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(character_id, turn_id, write_token)
            );
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS memories (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_type  TEXT NOT NULL,
                subject      TEXT NOT NULL DEFAULT 'user',
                predicate    TEXT NOT NULL DEFAULT '',
                content      TEXT NOT NULL,
                character_id TEXT NOT NULL DEFAULT '',
                stable_key   TEXT NOT NULL,
                importance   REAL NOT NULL DEFAULT 0.5,
                confidence   REAL NOT NULL DEFAULT 0.6,
                active       INTEGER NOT NULL DEFAULT 1,
                access_count INTEGER NOT NULL DEFAULT 0,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL,
                UNIQUE(character_id, stable_key, content)
            );
            CREATE INDEX IF NOT EXISTS idx_memories_scope
                ON memories(character_id, memory_type, active);

            CREATE TABLE IF NOT EXISTS character_states (
                character_id TEXT PRIMARY KEY,
                state_json   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS retrieval_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                character_id TEXT NOT NULL DEFAULT '',
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS initiative_topic_usage (
                character_id TEXT NOT NULL,
                memory_id TEXT NOT NULL,
                used_at REAL NOT NULL,
                PRIMARY KEY(character_id, memory_id)
            );
            CREATE TABLE IF NOT EXISTS usage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_id TEXT NOT NULL DEFAULT '',
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                cached_tokens INTEGER NOT NULL DEFAULT 0,
                estimated_cost_usd REAL NOT NULL DEFAULT 0,
                model TEXT NOT NULL DEFAULT '',
                context_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

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
        fact_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(facts)").fetchall()
        }
        if "character_id" not in fact_columns:
            conn.execute(
                "ALTER TABLE facts ADD COLUMN character_id TEXT DEFAULT ''"
            )
        log_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(logs)").fetchall()
        }
        if "turn_id" not in log_columns:
            conn.execute("ALTER TABLE logs ADD COLUMN turn_id TEXT")
        if "write_token" not in log_columns:
            conn.execute("ALTER TABLE logs ADD COLUMN write_token TEXT")
        if "history_uid" not in log_columns:
            conn.execute("ALTER TABLE logs ADD COLUMN history_uid TEXT")
        conn.execute(
            "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES (?, ?)",
            (4, datetime.now(timezone.utc).isoformat()),
        )
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

    def upsert_memory(
        self, *, memory_type: str, subject: str, predicate: str, content: str,
        character_id: str = "", importance: float = 0.5,
        confidence: float = 0.6, stable_key: str = "",
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        key = stable_key or f"{memory_type}:{subject}:{predicate}"
        conn = self._get_conn()
        current = conn.execute(
            "SELECT id, content FROM memories "
            "WHERE character_id = ? AND stable_key = ? AND active = 1",
            (character_id, key),
        ).fetchone()
        if current and current["content"] == content.strip():
            conn.execute(
                "UPDATE memories SET importance = MAX(importance, ?), "
                "confidence = MAX(confidence, ?), updated_at = ? WHERE id = ?",
                (importance, confidence, now, current["id"]),
            )
            conn.commit()
            return int(current["id"])
        if current:
            conn.execute("UPDATE memories SET active = 0, updated_at = ? WHERE id = ?",
                         (now, current["id"]))
        cursor = conn.execute(
            "INSERT INTO memories(memory_type, subject, predicate, content, "
            "character_id, stable_key, importance, confidence, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (memory_type, subject, predicate, content.strip(), character_id, key,
             importance, confidence, now, now),
        )
        conn.commit()
        return int(cursor.lastrowid)

    def list_memories(
        self, *, character_id: str = "", memory_type: str = "",
        active_only: bool = True, limit: int = 100,
    ) -> list[dict]:
        clauses, params = [], []
        if character_id:
            clauses.append("(character_id = ? OR character_id = '')")
            params.append(character_id)
        if memory_type:
            clauses.append("memory_type = ?")
            params.append(memory_type)
        if active_only:
            clauses.append("active = 1")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._get_conn().execute(
            "SELECT * FROM memories" + where +
            " ORDER BY importance DESC, updated_at DESC LIMIT ?", (*params, limit)
        ).fetchall()
        return [dict(row) for row in rows]

    def update_memory(
        self, memory_id: int, *, character_id: str = "",
        content: str | None = None, importance: float | None = None,
        confidence: float | None = None,
    ) -> dict | None:
        clauses, params = ["id = ?"], [int(memory_id)]
        if character_id:
            clauses.append("(character_id = ? OR character_id = '')")
            params.append(character_id)
        row = self._get_conn().execute(
            "SELECT * FROM memories WHERE " + " AND ".join(clauses), params
        ).fetchone()
        if not row:
            return None
        updates, values = [], []
        if content is not None and content.strip():
            updates.append("content = ?")
            values.append(content.strip())
        if importance is not None:
            updates.append("importance = ?")
            values.append(max(0.0, min(1.0, float(importance))))
        if confidence is not None:
            updates.append("confidence = ?")
            values.append(max(0.0, min(1.0, float(confidence))))
        if updates:
            updates.append("updated_at = ?")
            values.append(datetime.now(timezone.utc).isoformat())
            self._get_conn().execute(
                "UPDATE memories SET " + ", ".join(updates) + " WHERE id = ?",
                (*values, int(memory_id)),
            )
            self._get_conn().commit()
        refreshed = self._get_conn().execute(
            "SELECT * FROM memories WHERE id = ?", (int(memory_id),)
        ).fetchone()
        return dict(refreshed) if refreshed else None

    def forget_memory(self, memory_id: int, *, character_id: str = "") -> bool:
        clauses, params = ["id = ?"], [int(memory_id)]
        if character_id:
            clauses.append("(character_id = ? OR character_id = '')")
            params.append(character_id)
        cursor = self._get_conn().execute(
            "UPDATE memories SET active = 0, updated_at = ? WHERE "
            + " AND ".join(clauses),
            (datetime.now(timezone.utc).isoformat(), *params),
        )
        self._get_conn().commit()
        return cursor.rowcount > 0

    def search_memories(
        self, query: str, *, character_id: str = "", limit: int = 10
    ) -> list[dict]:
        from app.memory.retrieval import score_memory
        candidates = self.list_memories(character_id=character_id, limit=250)
        for fact in self.get_all_facts(character_id=character_id):
            candidates.append({
                "id": f"fact:{fact['id']}", "memory_type": "fact",
                "content": fact["fact"], "character_id": fact.get("character_id", ""),
                "importance": fact["importance"], "confidence": 0.7,
                "created_at": fact["created_at"], "updated_at": fact["created_at"],
            })
        ranked = []
        for item in candidates:
            def _ts(value):
                try:
                    return datetime.fromisoformat(str(value)).timestamp()
                except (ValueError, TypeError):
                    return 0.0
            item["created_ts"] = _ts(item.get("created_at"))
            item["updated_ts"] = _ts(item.get("updated_at"))
            score, reasons = score_memory(query, item)
            if score >= 0.24:
                item["score"] = round(score, 4)
                item["reasons"] = reasons or ["importance"]
                ranked.append(item)
        ranked.sort(key=lambda row: row["score"], reverse=True)
        results = ranked[:limit]
        now = datetime.now(timezone.utc).isoformat()
        self._get_conn().execute(
            "INSERT INTO retrieval_audit(query, character_id, result_json, created_at) "
            "VALUES (?, ?, ?, ?)",
            (query, character_id, json.dumps(
                {
                    "schemaVersion": 3,
                    "results": [
                        {
                            "id": row["id"],
                            "score": row["score"],
                            "reasons": row["reasons"],
                        }
                        for row in results
                    ],
                },
                ensure_ascii=False,
            ), now),
        )
        self._get_conn().commit()
        return results

    def save_character_state(self, character_id: str, state: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._get_conn().execute(
            "INSERT INTO character_states(character_id, state_json, updated_at) "
            "VALUES (?, ?, ?) ON CONFLICT(character_id) DO UPDATE SET "
            "state_json = excluded.state_json, updated_at = excluded.updated_at",
            (
                character_id,
                json.dumps(
                    {"schemaVersion": 3, **state},
                    ensure_ascii=False,
                ),
                now,
            ),
        )
        self._get_conn().commit()

    def load_character_state(self, character_id: str) -> dict:
        row = self._get_conn().execute(
            "SELECT state_json FROM character_states WHERE character_id = ?",
            (character_id,),
        ).fetchone()
        if not row:
            return {}
        try:
            state = json.loads(row["state_json"])
            if not isinstance(state, dict) or state.get("schemaVersion") != 3:
                return {}
            return {
                key: value
                for key, value in state.items()
                if key != "schemaVersion"
            }
        except (json.JSONDecodeError, TypeError):
            return {}

    def backfill_legacy_facts(self) -> int:
        """Copy legacy facts into the lifecycle table without deleting originals."""
        from app.memory.lifecycle import store_candidates
        before = len(self.list_memories(active_only=False, limit=100000))
        for fact in self.get_all_facts():
            store_candidates(self, [{
                "fact": fact["fact"],
                "importance": fact["importance"],
                "confidence": 0.7,
            }], character_id=fact.get("character_id", ""))
        after = len(self.list_memories(active_only=False, limit=100000))
        return max(0, after - before)

    def initiative_last_used(self, character_id: str, memory_id: object) -> float:
        row = self._get_conn().execute(
            "SELECT used_at FROM initiative_topic_usage "
            "WHERE character_id = ? AND memory_id = ?",
            (character_id, str(memory_id)),
        ).fetchone()
        return float(row["used_at"]) if row else 0.0

    def mark_initiative_used(self, character_id: str, memory_id: object) -> None:
        self._get_conn().execute(
            "INSERT INTO initiative_topic_usage(character_id, memory_id, used_at) "
            "VALUES (?, ?, ?) ON CONFLICT(character_id, memory_id) "
            "DO UPDATE SET used_at = excluded.used_at",
            (character_id, str(memory_id), __import__("time").time()),
        )
        self._get_conn().commit()

    def record_usage(
        self, character_id: str, usage: dict, context_budget: dict | None = None
    ) -> None:
        self._get_conn().execute(
            "INSERT INTO usage_events(character_id, prompt_tokens, completion_tokens, "
            "cached_tokens, estimated_cost_usd, model, context_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                character_id,
                int(usage.get("prompt_tokens", 0) or 0),
                int(usage.get("completion_tokens", 0) or 0),
                int(usage.get("cached_tokens", 0) or 0),
                float(usage.get("estimated_cost_usd", 0) or 0),
                str(usage.get("model", "")),
                json.dumps(
                    {"schemaVersion": 3, **(context_budget or {})},
                    ensure_ascii=False,
                ),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._get_conn().commit()

    def usage_summary(self, character_id: str = "", recent_limit: int = 30) -> dict:
        where, params = "", []
        if character_id:
            where = " WHERE character_id = ?"
            params.append(character_id)
        totals = self._get_conn().execute(
            "SELECT COUNT(*) turns, COALESCE(SUM(prompt_tokens), 0) prompt_tokens, "
            "COALESCE(SUM(completion_tokens), 0) completion_tokens, "
            "COALESCE(SUM(cached_tokens), 0) cached_tokens, "
            "COALESCE(SUM(estimated_cost_usd), 0) estimated_cost_usd "
            "FROM usage_events" + where, params,
        ).fetchone()
        rows = self._get_conn().execute(
            "SELECT prompt_tokens, completion_tokens, cached_tokens, "
            "estimated_cost_usd, model, context_json, created_at FROM usage_events"
            + where + " ORDER BY id DESC LIMIT ?",
            (*params, max(1, min(200, int(recent_limit)))),
        ).fetchall()
        return {
            "totals": dict(totals),
            "recent": [
                {
                    **{key: row[key] for key in row.keys() if key != "context_json"},
                    "context_budget": {
                        key: value
                        for key, value in json.loads(
                            row["context_json"] or "{}"
                        ).items()
                        if key != "schemaVersion"
                    },
                }
                for row in rows
            ],
        }

    def record_usage(
        self, character_id: str, usage: dict, context_budget: dict | None = None
    ) -> None:
        self._get_conn().execute(
            "INSERT INTO usage_events(character_id, prompt_tokens, completion_tokens, "
            "cached_tokens, estimated_cost_usd, model, context_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                character_id,
                int(usage.get("prompt_tokens", 0) or 0),
                int(usage.get("completion_tokens", 0) or 0),
                int(usage.get("cached_tokens", 0) or 0),
                float(usage.get("estimated_cost_usd", 0) or 0),
                str(usage.get("model", "")),
                json.dumps(
                    {"schemaVersion": 3, **(context_budget or {})},
                    ensure_ascii=False,
                ),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._get_conn().commit()

    def usage_summary(self, character_id: str = "", recent_limit: int = 30) -> dict:
        where, params = "", []
        if character_id:
            where = " WHERE character_id = ?"
            params.append(character_id)
        totals = self._get_conn().execute(
            "SELECT COUNT(*) turns, COALESCE(SUM(prompt_tokens), 0) prompt_tokens, "
            "COALESCE(SUM(completion_tokens), 0) completion_tokens, "
            "COALESCE(SUM(cached_tokens), 0) cached_tokens, "
            "COALESCE(SUM(estimated_cost_usd), 0) estimated_cost_usd "
            "FROM usage_events" + where, params,
        ).fetchone()
        rows = self._get_conn().execute(
            "SELECT prompt_tokens, completion_tokens, cached_tokens, "
            "estimated_cost_usd, model, context_json, created_at FROM usage_events"
            + where + " ORDER BY id DESC LIMIT ?",
            (*params, max(1, min(200, int(recent_limit)))),
        ).fetchall()
        return {
            "totals": dict(totals),
            "recent": [
                {
                    **{key: row[key] for key in row.keys() if key != "context_json"},
                    "context_budget": {
                        key: value
                        for key, value in json.loads(
                            row["context_json"] or "{}"
                        ).items()
                        if key != "schemaVersion"
                    },
                }
                for row in rows
            ],
        }

    # ── conversation log ───────────────────────────────────────────────

    def log_turn(
        self,
        user_text: str,
        reply: dict,
        character_id: str = "",
        *,
        turn_id: str = "",
        write_token: str = "",
        history_uid: str = "",
    ) -> bool:
        """Atomically persist one turn; return False for an idempotent replay."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            if turn_id and write_token:
                inserted = conn.execute(
                    "INSERT OR IGNORE INTO turn_commits"
                    "(character_id, turn_id, write_token, created_at) VALUES (?, ?, ?, ?)",
                    (character_id, turn_id, write_token, now),
                )
                if inserted.rowcount == 0:
                    conn.rollback()
                    return False
            if user_text.strip():
                conn.execute(
                    "INSERT INTO logs(role, content, intent, character_id, turn_id, write_token, history_uid, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "user", user_text[:1000], reply.get("intent", "unknown"),
                        character_id, turn_id or None, write_token or None,
                        history_uid or None, now,
                    ),
                )
            reply_text = reply.get("reply_text", "")[:2000]
            if reply_text.strip():
                conn.execute(
                    "INSERT INTO logs(role, content, intent, character_id, turn_id, write_token, history_uid, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "assistant", reply_text, reply.get("intent", "reply"),
                        character_id, turn_id or None, write_token or None,
                        history_uid or None, now,
                    ),
                )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise

    def history_messages(
        self,
        history_uid: str,
        *,
        character_id: str = "",
    ) -> list[dict[str, str]]:
        rows = self._get_conn().execute(
            "SELECT role, content FROM logs "
            "WHERE history_uid = ? AND (? = '' OR character_id = ?) ORDER BY id",
            (history_uid, character_id, character_id),
        ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    def delete_history(self, history_uid: str, *, character_id: str = "") -> int:
        conn = self._get_conn()
        cur = conn.execute(
            "DELETE FROM logs WHERE history_uid = ? AND (? = '' OR character_id = ?)",
            (history_uid, character_id, character_id),
        )
        conn.commit()
        return cur.rowcount

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
        character_id: str = "",
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
            "INSERT INTO facts(fact, tags, time, source, importance, character_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (content.strip(), json.dumps(tags, ensure_ascii=False), time, source,
             importance, character_id, now),
        )
        conn.commit()
        return True

    def _find_overlapping(self, content: str, tags: list[str]) -> bool:
        conn = self._get_conn()
        normalized = re.sub(r"\s+", "", content).lower()
        rows = conn.execute("SELECT fact FROM facts").fetchall()
        return any(re.sub(r"\s+", "", row["fact"]).lower() == normalized for row in rows)

    def search_facts(
        self,
        query: str = "",
        tags: Optional[list[str]] = None,
        k: int = 5,
        character_id: str = "",
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
                    scope = " AND (f.character_id = ? OR f.character_id = '')" if character_id else ""
                    rows = conn.execute(
                        "SELECT f.* FROM facts_fts fts JOIN facts f ON fts.rowid = f.id "
                        "WHERE facts_fts MATCH ?" + scope + " ORDER BY rank LIMIT ?",
                        ((fts_query, character_id, _FTS_LIMIT) if character_id
                         else (fts_query, _FTS_LIMIT)),
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
            scope = " AND (character_id = ? OR character_id = '')" if character_id else ""
            rows = conn.execute(
                "SELECT * FROM facts WHERE fact LIKE ?" + scope
                + " ORDER BY importance DESC LIMIT ?",
                ((f"%{query}%", character_id, _FTS_LIMIT) if character_id
                 else (f"%{query}%", _FTS_LIMIT)),
            ).fetchall()
            for r in rows:
                if r["id"] in seen_ids:
                    continue
                results.append(self._row_to_fact(r))

        return results[:k]

    def get_all_facts(self, character_id: str = "") -> list[dict]:
        conn = self._get_conn()
        if character_id:
            rows = conn.execute(
                "SELECT * FROM facts WHERE character_id = ? OR character_id = '' "
                "ORDER BY importance DESC, created_at DESC", (character_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM facts ORDER BY importance DESC, created_at DESC"
            ).fetchall()
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
            "character_id": r["character_id"] if "character_id" in r.keys() else "",
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



