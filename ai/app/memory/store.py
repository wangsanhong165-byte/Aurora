"""Simple memory store - conversation log + important facts.

Replaces the old 9-file pipeline with a straightforward dual-layer design:

Layer 1 - Conversation log (memory.jsonl):
    Append-only log of every turn. Used for recent context in prompts.

Layer 2 - Important facts (facts.jsonl):
    Key facts about the user and relationship, added sparingly.
    Retrieved via simple keyword matching at query time.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any


class MemoryStore:
    """Simple dual-layer memory store."""

    def __init__(self, base_dir=None, max_log_turns=500, max_facts=200):
        base = base_dir or Path(__file__).resolve().parents[2]
        self._log_path = base / "memory" / "memory.jsonl"
        self._facts_path = base / "memory" / "facts.jsonl"
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._max_log_turns = max_log_turns
        self._max_facts = max_facts
        self._llm_adapter = None

    def set_llm_adapter(self, adapter):
        self._llm_adapter = adapter

    def log_turn(self, user_text, reply):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "created_at": now,
            "user": user_text,
            "assistant": reply.get("reply_text", ""),
            "intent": reply.get("intent", "unknown"),
        }
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._trim_log_if_needed()

    def enqueue_turn(self, user_text, reply):
        self.log_turn(user_text, reply)

    def recent_turns(self, n=10):
        if not self._log_path.exists(): return []
        rows = []
        with self._log_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try: rows.append(json.loads(line))
                except: continue
        return rows[-n:]

    def _trim_log_if_needed(self):
        rows = self.recent_turns(0)
        if len(rows) <= self._max_log_turns: return
        keep = rows[-self._max_log_turns:]
        with self._log_path.open("w", encoding="utf-8") as f:
            for row in keep:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def add_fact(self, content, importance=0.5, source=""):
        if not content or len(content) < 3: return
        from datetime import datetime, timezone
        fact = {"content": content, "importance": importance, "source": source,
                "created_at": datetime.now(timezone.utc).isoformat()}
        existing = self._load_facts()
        if self._is_duplicate(content, existing): return
        existing.append(fact)
        self._save_facts(existing)

    def search_facts(self, query, k=5):
        facts = self._load_facts()
        if not facts or not query: return []
        query_tokens = set(_tokenize(query))
        if not query_tokens: return []
        scored = []
        for fact in facts:
            content = str(fact.get("content", ""))
            fact_tokens = set(_tokenize(content))
            if not fact_tokens: continue
            inter = len(query_tokens & fact_tokens)
            union_ = len(query_tokens | fact_tokens)
            score = inter / union_ if union_ else 0
            score *= (0.5 + float(fact.get("importance", 0.5)))
            scored.append((score, fact))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [f for s, f in scored[:k] if s > 0.02]

    def sample_facts(self, n=3):
        facts = self._load_facts()
        if not facts: return []
        if len(facts) <= n: return facts
        weights = [float(f.get("importance", 0.3)) + 0.1 for f in facts]
        sampled = random.choices(facts, weights=weights, k=min(n * 2, len(facts)))
        seen = set()
        result = []
        for f in sampled:
            c = f.get("content", "")
            if c and c not in seen: seen.add(c); result.append(f)
            if len(result) >= n: break
        return result

    def _load_facts(self):
        if not self._facts_path.exists(): return []
        facts = []
        with self._facts_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try: facts.append(json.loads(line))
                except: continue
        return facts

    def _save_facts(self, facts):
        if len(facts) > self._max_facts:
            facts.sort(key=lambda f: float(f.get("importance", 0)), reverse=True)
            facts = facts[:self._max_facts]
        with self._facts_path.open("w", encoding="utf-8") as f:
            for fact in facts: f.write(json.dumps(fact, ensure_ascii=False) + "\n")

    @staticmethod
    def _is_duplicate(content, existing):
        tokens = set(content)
        for fact in existing:
            ft = set(str(fact.get("content", "")))
            if not tokens or not ft: continue
            inter = len(tokens & ft)
            union_ = len(tokens | ft)
            if union_ and inter / union_ > 0.55: return True
        return False

    def build_prompt_context(self, query="", max_recent_turns=5, max_facts=3):
        sections = []
        turns = self.recent_turns(max_recent_turns)
        if turns:
            lines = ["\n[最近对话]"]
            for t in turns:
                u = str(t.get("user", "")).strip()
                a = str(t.get("assistant", "")).strip()
                if u: lines.append("用户: " + u[:200])
                if a: lines.append("Monika: " + a[:200])
            sections.append("\n".join(lines))
        seen = set()
        fact_lines = []
        if query:
            for f in self.search_facts(query, k=max_facts):
                c = str(f.get("content", ""))
                if c and c not in seen: seen.add(c); fact_lines.append("  " + c)
        if len(fact_lines) < max_facts:
            for f in self.sample_facts(max_facts):
                c = str(f.get("content", ""))
                if c and c not in seen: seen.add(c); fact_lines.append("  " + c)
        if fact_lines:
            sections.append("\n[记忆]\n" + "\n".join(fact_lines[:max_facts]))
        return "\n".join(sections)

    def rebuild_index(self):
        return len(self._load_facts())

    def start(self): pass
    def stop(self, wait=False): pass

    def summarize_session(self, llm_adapter=None):
        adapter = llm_adapter or self._llm_adapter
        if not adapter: return
        turns = self.recent_turns(30)
        if not turns or len(turns) < 3: return
        lines = []
        for t in turns[-20:]:
            u = str(t.get("user", "")).strip()
            a = str(t.get("assistant", "")).strip()
            if u: lines.append("User: " + u)
            if a: lines.append("Monika: " + a)
        conv = "\n".join(lines)
        if len(conv) < 20: return
        prompt = ("Summarise this conversation session into 1-2 sentences.\n"
                  "Focus on: what was discussed, any decisions made, user mood or state.\n"
                  "Write in Chinese, from Monika first-person perspective.\n"
                  "Conversation:\n" + conv + "\n\nEpisode summary:")
        try:
            result = adapter.generate({"messages": [{"role": "user", "content": prompt}], "temperature": 0.3}, timeout=10)
            summary = str(result.get("content", "")).strip()
            if summary and len(summary) > 5: self.add_fact(summary, importance=0.8, source="session_summary")
        except: pass


def _tokenize(text):
    tokens = []
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff" or "\u3040" <= ch <= "\u30ff":
            tokens.append(ch)
    words = __import__("re").findall(r"[a-zA-Z0-9]+", text.lower())
    tokens.extend(w for w in words if len(w) >= 2)
    return tokens


memory_store = MemoryStore()
