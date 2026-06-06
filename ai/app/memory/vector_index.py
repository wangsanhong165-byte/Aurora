"""Vector index  rebuildable search index over long-term memory.

NOT the primary store. The LongTermMemoryStore is the source of truth.
This index is rebuilt from it and used for semantic search at query time.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from app.memory.long_term import LongTermMemoryStore


class VectorIndex:
    """Rebuildable TF-IDF index over memory cards."""

    def __init__(self) -> None:
        self._cards: list[dict[str, Any]] = []
        self._idf: dict[str, float] = {}
        self._tfidf_vectors: list[dict[str, float]] = []
        self._built = False

    # ---- build -----------------------------------------------------------
    def build(self, cards: list[dict[str, Any]]) -> None:
        self._cards = list(cards)
        if not cards:
            self._built = False
            return

        docs = [_tokenize(str(c.get("content", ""))) for c in cards]

        n_docs = len(docs)
        df: Counter[str] = Counter()
        for tokens in docs:
            df.update(set(tokens))

        self._idf = {
            term: math.log((n_docs + 1) / (freq + 1)) + 1.0
            for term, freq in df.items()
        }

        self._tfidf_vectors = []
        for tokens in docs:
            tf = Counter(tokens)
            max_tf = max(tf.values()) if tf else 1
            vec = {
                term: (count / max_tf) * self._idf.get(term, 0.0)
                for term, count in tf.items()
            }
            self._tfidf_vectors.append(vec)

        self._built = True

    # ---- search ----------------------------------------------------------
    def search(
        self,
        query: str,
        k: int = 5,
        min_score: float = 0.05,
    ) -> list[dict[str, Any]]:
        if not self._built:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        tf = Counter(query_tokens)
        max_tf = max(tf.values()) if tf else 1
        query_vec = {
            term: (count / max_tf) * self._idf.get(term, 0.0)
            for term, count in tf.items()
        }

        results: list[dict[str, Any]] = []
        for i, doc_vec in enumerate(self._tfidf_vectors):
            score = _cosine(query_vec, doc_vec)
            if score >= min_score:
                results.append({"card": self._cards[i], "score": round(score, 4)})

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:k]

    def rebuild_from_store(self, store: LongTermMemoryStore | None = None) -> int:
        """Rebuild index from LongTermMemoryStore. Returns card count."""
        if store is None:
            store = LongTermMemoryStore()
        cards = store.load()
        self.build(cards)
        return len(cards)

    # ---- persistence -----------------------------------------------------
    def save(self, path: Path) -> None:
        data = {"cards": self._cards, "idf": self._idf}
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, path: Path) -> None:
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        self._cards = data.get("cards", [])
        self._idf = data.get("idf", {})
        self.build(self._cards)

    @property
    def size(self) -> int:
        return len(self._cards)

    @property
    def built(self) -> bool:
        return self._built


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    cjk_chars: list[str] = []
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff' or '\u3040' <= ch <= '\u30ff':
            cjk_chars.append(ch)
        else:
            if cjk_chars:
                for i in range(len(cjk_chars)):
                    tokens.append(cjk_chars[i])
                    if i + 1 < len(cjk_chars):
                        tokens.append(cjk_chars[i] + cjk_chars[i + 1])
                cjk_chars = []
    if cjk_chars:
        for i in range(len(cjk_chars)):
            tokens.append(cjk_chars[i])
            if i + 1 < len(cjk_chars):
                tokens.append(cjk_chars[i] + cjk_chars[i + 1])

    import re
    words = re.findall(r'[a-zA-Z0-9]+', text.lower())
    tokens.extend(words)
    for w in words:
        if len(w) >= 3:
            tokens.append(w)

    return [t for t in tokens if len(t) >= 1]


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in set(a) | set(b))
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# Global singleton
memory_index = VectorIndex()
