"""Memory ticker — turn-based memory scheduler.

Trigger mechanism (openhanako v3 inspired, adapted for single-agent):
  - Every N turns: rolling summary + compile_today + assemble
  - Date change: daily batch (week + longterm + facts + assemble)
  - Startup: recover any unprocessed turns

All operations run as fire-and-forget background tasks.
"""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional, Callable

from app.memory.store import memory_store
from app.memory.extractor import run_extraction_pipeline
from app.memory.compiler import (
    compile_today_and_assemble,
    compile_and_assemble,
    set_llm_adapter,
)

_TURNS_PER_SUMMARY = 10
_DAILY_CHECK_SECONDS = 3600  # check every hour for date change


class MemoryTicker:
    """Turn-based memory scheduler (fire-and-forget background tasks)."""

    def __init__(self, llm_adapter: Any = None):
        self._llm_adapter = llm_adapter
        self._turn_count = 0
        self._last_date = datetime.now(timezone.utc).date()
        self._last_extraction_time = 0.0  # throttle: min seconds between extractions
        self._stopped = False
        self._timer: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def set_llm_adapter(self, adapter: Any):
        self._llm_adapter = adapter
        set_llm_adapter(adapter)

    # ── public API ────────────────────────────────────────────────

    def notify_turn(self):
        """Called after each completed turn."""
        if self._stopped:
            return
        if not self._llm_adapter:
            return

        with self._lock:
            self._turn_count += 1
            count = self._turn_count

        # Check date change
        self._check_date_change()

        # Every N turns: run extraction + compile_today
        if count % _TURNS_PER_SUMMARY == 0:
            self._run_background(self._on_turn_threshold)

    def notify_session_end(self):
        """Called when a session ends (e.g., user goes idle)."""
        if self._stopped or not self._llm_adapter:
            return
        self._run_background(self._on_session_end)

    def start(self):
        """Start the daily check timer."""
        self._stopped = False
        self._daily_check()

    def stop(self, wait: bool = False):
        """Stop the ticker."""
        self._stopped = True

    # ── background tasks ──────────────────────────────────────────

    def _run_background(self, fn: Callable):
        """Run a task in a background thread (fire-and-forget)."""
        t = threading.Thread(target=fn, daemon=True)
        t.start()

    def _on_turn_threshold(self):
        """Every N turns: extract facts + compile today."""
        now = time.time()
        if now - self._last_extraction_time < 30:
            return
        self._last_extraction_time = now

        char_name = self._get_char_name()
        stats = run_extraction_pipeline(self._llm_adapter, character_name=char_name)
        if stats.get("facts_stored", 0) > 0 or stats.get("summary"):
            compile_today_and_assemble()

    def _on_session_end(self):
        """Session ended: final extraction + compile today."""
        char_name = self._get_char_name()
        stats = run_extraction_pipeline(self._llm_adapter, character_name=char_name)
        compile_today_and_assemble()

    # ── daily job ─────────────────────────────────────────────────

    def _check_date_change(self):
        """Check if the date has changed. If so, run daily batch."""
        today = datetime.now(timezone.utc).date()
        if today != self._last_date:
            self._last_date = today
            self._run_background(self._on_daily)

    def _on_daily(self):
        """Daily batch: compile week + longterm + facts + assemble."""
        compile_and_assemble()

    def _daily_check(self):
        """Periodic timer to catch date changes during idle periods."""
        if self._stopped:
            return

        self._check_date_change()

        self._timer = threading.Timer(_DAILY_CHECK_SECONDS, self._daily_check)
        self._timer.daemon = True
        self._timer.start()

    # ── recovery ──────────────────────────────────────────────────

    def _get_char_name(self) -> str:
        """Get active character display name for prompt generation."""
        try:
            from app.memory.compiler import get_active_char_id, _char_name_from_id
            cid = get_active_char_id()
            return _char_name_from_id(cid)
        except Exception:
            return ""

    def recover(self):
        """Startup recovery: estimate unprocessed turns."""
        if not self._llm_adapter:
            return
        turns = memory_store.recent_turns(_TURNS_PER_SUMMARY)
        if len(turns) >= _TURNS_PER_SUMMARY // 2:
            with self._lock:
                self._turn_count = len(turns)
            self._run_background(self._on_turn_threshold)

