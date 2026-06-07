"""Background memory pipeline.

Pipeline:
    Conversation → ShortTerm (raw log)
         │
         ▼
    Extractor (LLM, async)
         │
         ▼
    CandidateMemory (buffer, N cards or T seconds)
         │
         ▼
    Merger (dedup with existing LongTerm)
         │
         ▼
    LongTermMemory (persist)
         │
         ▼
    VectorIndex (rebuild)
"""

from __future__ import annotations

import json
import queue
import threading
from dataclasses import dataclass
from typing import Any

from app.core.event_bus import bus
from app.core.events import EventType
from app.memory.long_term import LongTermMemoryStore, MemoryCard
from app.memory.short_term import ShortTermMemory
from app.memory.extractor import MemoryExtractor
from app.memory.merger import MemoryMerger
from app.memory.candidate import CandidateMemory


@dataclass(slots=True)
class MemoryJob:
    user_text: str
    reply: dict[str, Any]
    source: str = "conversation"


class BackgroundMemoryWorker:
    """Single-threaded memory pipeline worker."""

    def __init__(
        self,
        short_term: ShortTermMemory | None = None,
        long_term: LongTermMemoryStore | None = None,
        extractor: MemoryExtractor | None = None,
        merger: MemoryMerger | None = None,
        candidate: CandidateMemory | None = None,
    ) -> None:
        self.short_term = short_term or ShortTermMemory()
        self.long_term = long_term or LongTermMemoryStore()
        self.extractor = extractor or MemoryExtractor()
        self.merger = merger or MemoryMerger()
        self.candidate = candidate or CandidateMemory()
        self._queue: queue.Queue[MemoryJob | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._running = False

    def set_llm_adapter(self, adapter: Any) -> None:
        self.extractor.set_adapter(adapter)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self, wait: bool = False) -> None:
        if not self._running:
            return
        self._queue.put(None)
        if wait and self._thread:
            self._thread.join(timeout=5.0)
        self._running = False
        self._thread = None

    def enqueue_turn(self, user_text: str, reply: dict[str, Any]) -> None:
        """Record turn and queue for background extraction."""
        self.short_term.append(user_text, reply)
        self.start()
        self._queue.put(MemoryJob(user_text=user_text, reply=reply))
        bus.publish(
            EventType.MEMORY_BACKGROUND_QUEUED,
            {"user_text": user_text[:80]},
            source="memory",
        )

    def rebuild_index(self) -> int:
        from app.memory.vector_index import memory_index
        return memory_index.rebuild_from_store(self.long_term)

    def _loop(self) -> None:
        while True:
            job = self._queue.get()
            if job is None:
                self._queue.task_done()
                # Final flush on stop
                self._flush_candidates()
                break
            try:
                # 1. Extract new cards from recent conversation
                turns = self.short_term.load(limit=10)
                new_cards = self.extractor.extract(turns)

                # 2. Buffer into CandidateMemory
                if new_cards:
                    self.candidate.extend(new_cards)
                    bus.publish(
                        EventType.LOG,
                        {"message": f"Candidates buffered: {len(new_cards)} new, {self.candidate.count} total"},
                        source="memory",
                    )

                # 3. Flush if threshold reached
                if self.candidate.should_flush(min_cards=5, max_age_sec=300):
                    self._flush_candidates()

            finally:
                self._queue.task_done()

    def _flush_candidates(self) -> None:
        """Drain candidates, merge, persist, rebuild index."""
        pending = self.candidate.drain()
        if not pending:
            return

        existing = self.long_term.load()
        merged = self.merger.merge(existing, pending)
        self._write_all(merged)

        # Rebuild index
        from app.memory.vector_index import memory_index
        memory_index.build(merged)

        bus.publish(
            EventType.MEMORY_BACKGROUND_FINISHED,
            {"candidates": len(pending), "total": len(merged)},
            source="memory",
        )
        print(f"[Memory] Flushed {len(pending)} candidates → {len(merged)} total cards")

    def summarize_session(self, llm_adapter: Any) -> None:
        """Generate a session-level episode summary and write it to long-term memory.

        Called on shutdown. Reads recent turns from short-term memory,
        asks the LLM to produce a 1-2 sentence summary, and stores it
        as an episode MemoryCard (protected from trimming).
        """
        turns = self.short_term.load(limit=0)
        if not turns:
            return

        # Format turns into readable conversation
        lines = []
        for t in turns[-30:]:
            user = str(t.get("user", "")).strip()
            assistant = str(t.get("assistant", "")).strip()
            if user:
                lines.append("User: " + user)
            if assistant:
                lines.append("Monika: " + assistant)
        conv = chr(10).join(lines)
        if len(conv) < 20:
            return

        prompt = (
            "Summarise this conversation session into 1-2 sentences.\n"
            "Focus on: what was discussed, any decisions made, user mood or state.\n"
            "Write in Chinese, from Monika first-person perspective.\n"
            "Example: \u6211\u548c\u7528\u6237\u8ba8\u8bba\u4e86Monika\u4eba\u683c\u7cfb\u7edf\uff0c\u51b3\u5b9a\u524a\u5f31\u5b64\u72ec\u5c5e\u6027\u3002\n"
            "\nConversation:\n" + conv + "\n\n"
            "Episode summary:"
        )

        try:
            result = llm_adapter.generate(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            summary = str(result.get("content", "")).strip()
            if not summary or len(summary) < 5:
                return
        except Exception:
            return

        card = MemoryCard(
            type="episode",
            content=summary,
            importance=0.9,
            confidence=0.8,
            source="session_summary",
        )
        self.long_term.append(card)
        print("[Episode] Session summary: " + summary[:80] + "...")

    def _write_all(self, cards: list[dict[str, Any]]) -> None:
        path = self.long_term.path
        with path.open("w", encoding="utf-8") as file:
            for row in cards:
                file.write(json.dumps(row, ensure_ascii=False) + "\n")


memory_worker = BackgroundMemoryWorker()
