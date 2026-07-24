"""Runtime Management — auxiliary operations owned by the Runtime.

All history CRUD, pinned memories, character switching, and prompt
reloading logic lives here. The Transport layer calls into this module
through thin dispatchers — it never duplicates this logic.

This is the SINGLE SOURCE OF TRUTH for management operations.
Both the Transport server and the legacy Bridge server delegate here.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.runtime.runtime import runtime as default_runtime

logger = logging.getLogger("runtime.management")


class RuntimeManager:
    """Manages auxiliary operations on behalf of the Companion Runtime.

    Provides a clean API that both Transport and legacy Bridge can call.
    All state is file-backed (persisted across server restarts).
    """

    def __init__(self, base_dir: Path | None = None, runtime=None):
        self._runtime = runtime or default_runtime
        self._base_dir = base_dir or Path(__file__).resolve().parent.parent.parent

        # History state
        self._histories_dir = self._base_dir / "data" / "memory" / "histories"
        self._history_index: dict[str, dict] = {}
        self._current_history_uid: str = ""

        # Pinned memories
        self._pinned_cache: str = ""
        self._pinned_path: Path | None = None

        self._ensure_dirs()

    # ── Initialization ──────────────────────────────────────────────

    def _ensure_dirs(self) -> None:
        """Ensure data directories for histories exist."""
        self._histories_dir.mkdir(parents=True, exist_ok=True)
        index_path = self._histories_dir / "index.json"
        if index_path.exists():
            try:
                self._history_index = json.loads(index_path.read_text("utf-8"))
            except Exception:
                self._history_index = {}
        else:
            self._history_index = {}
            index_path.write_text("{}", encoding="utf-8")

    def get_character_id(self) -> str:
        """Get the active character ID from the runtime."""
        try:
            info = self._runtime.get_character_info()
            card = info.get("card", {})
            return card.get("id", "monika")
        except Exception:
            return "monika"

    def ensure_pinned(self) -> Path:
        """Ensure pinned.md path exists for current character. Returns the path."""
        if self._pinned_path is not None:
            return self._pinned_path
        cid = self.get_character_id()
        path = self._base_dir / "config" / "characters" / cid / "pinned.md"
        self._pinned_path = path
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
        self._pinned_cache = path.read_text("utf-8").strip()
        return path

    def reinit_per_character(self) -> None:
        """Re-initialize per-character state (called after character switch)."""
        self._pinned_path = None
        self._pinned_cache = ""
        self.ensure_pinned()
        self._current_history_uid = ""
        self._ensure_dirs()

    # ── History operations ──────────────────────────────────────────

    def _save_index(self) -> None:
        """Persist history index to disk."""
        (self._histories_dir / "index.json").write_text(
            json.dumps(self._history_index, ensure_ascii=False), encoding="utf-8"
        )

    def _load_messages(self, uid: str) -> list[dict]:
        """Load messages for a given history UID."""
        path = self._histories_dir / f"{uid}.json"
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text("utf-8"))
        except Exception:
            return []

    def get_history_list(self) -> list[dict]:
        """Return histories sorted by timestamp desc."""
        result = []
        for uid, info in self._history_index.items():
            result.append({
                "uid": uid,
                "latest_message": info.get("latest_message"),
                "timestamp": info.get("timestamp", ""),
            })
        result.sort(key=lambda x: x["timestamp"], reverse=True)
        return result

    def load_history(self, history_uid: str) -> dict:
        """Load a history by UID and restore conversation state. Returns messages."""
        self._current_history_uid = history_uid
        messages = self._load_messages(history_uid)

        # Restore conversation in runtime
        try:
            conv = getattr(self._runtime, "conversation", None)
            if conv is not None:
                if hasattr(conv, "clear"):
                    conv.clear()
                for m in messages:
                    role = m.get("role", "")
                    content = m.get("content", "")
                    if role in ("user", "assistant") and content:
                        conv.add_turn({"role": role, "content": content})
        except Exception as e:
            logger.warning("Failed to restore conversation: %s", e)

        return {"history_uid": history_uid, "messages": messages}

    def create_history(self) -> dict:
        """Create a new history UID and return it."""
        uid = f"hist_{uuid.uuid4().hex[:12]}"
        self._current_history_uid = uid
        now = datetime.now(timezone.utc).isoformat()
        self._history_index[uid] = {"timestamp": now, "latest_message": None}
        self._save_index()

        # Clear runtime conversation
        try:
            conv = getattr(self._runtime, "conversation", None)
            if conv is not None and hasattr(conv, "clear"):
                conv.clear()
        except Exception:
            pass

        return {"history_uid": uid}

    def delete_history(self, history_uid: str) -> dict:
        """Delete a history by UID. Returns success status."""
        path = self._histories_dir / f"{history_uid}.json"
        if path.exists():
            path.unlink()

        existed = history_uid in self._history_index
        self._history_index.pop(history_uid, None)
        self._save_index()

        if self._current_history_uid == history_uid:
            self._current_history_uid = ""

        return {"success": existed, "history_uid": history_uid}

    def save_to_current_history(self, user_text: str, assistant_text: str) -> None:
        """Append a user+assistant exchange to the current history file."""
        import json as _json

        if not self._current_history_uid:
            # Auto-create if none exists
            res = self.create_history()
            # Re-fetch
            self._current_history_uid = res["history_uid"]

        messages = self._load_messages(self._current_history_uid)
        messages.append({"role": "user", "content": user_text})
        messages.append({"role": "assistant", "content": assistant_text})

        path = self._histories_dir / f"{self._current_history_uid}.json"
        path.write_text(_json.dumps(messages, ensure_ascii=False), encoding="utf-8")

        # Update index
        ts = datetime.now(timezone.utc).isoformat()
        preview = (user_text[:80] + "...") if len(user_text) > 80 else user_text
        self._history_index[self._current_history_uid] = {
            "timestamp": ts,
            "latest_message": preview,
        }
        self._save_index()

    # ── Pinned memories ─────────────────────────────────────────────

    def get_pinned(self) -> str:
        """Return the current pinned memories content."""
        self.ensure_pinned()
        return self._pinned_cache

    def set_pinned(self, content: str) -> str:
        """Update pinned memories content. Returns the new content."""
        path = self.ensure_pinned()
        self._pinned_cache = content
        path.write_text(content, encoding="utf-8")
        logger.info("[Pinned] Updated (%d chars)", len(content))
        return content

    # ── Character switching ─────────────────────────────────────────

    def switch_character(self, character_id: str) -> dict:
        """Switch the active character. Returns result dict."""
        if not character_id.strip():
            return {"error": "switch_character requires character_id"}

        try:
            result = self._runtime.switch_character(character_id)
            if "error" in result:
                logger.error("[Switch] Failed: %s", result["error"])
                return result

            info = self._runtime.get_character_info()
            char_name = info.get("name", "AI")

            # Re-init per-character state
            self.reinit_per_character()

            # Reload prompts
            try:
                from app.prompts.loader import reload_cache as _reload_cache
                _reload_cache()
            except Exception:
                pass

            logger.info("[Switch] Character switched to: %s", char_name)

            return {
                "character_id": character_id,
                "character_name": char_name,
            }

        except Exception as e:
            logger.error("[Switch] Error: %s", e)
            return {"error": str(e)}

    def reload_prompts(self) -> None:
        """Reload prompt templates from disk."""
        try:
            from app.prompts.loader import reload_cache as _reload_cache
            _reload_cache()
            logger.info("[Prompts] Cache cleared")
        except Exception as e:
            logger.warning("[Prompts] Reload failed: %s", e)

    # ── Proactive system ─────────────────────────────────────────────

    def set_proactive(self, enabled: bool) -> None:
        """Enable or disable the proactive initiative system."""
        try:
            ic = getattr(self._runtime, "initiative_checker", None)
            if ic is not None:
                if enabled:
                    ic.start()
                else:
                    ic.stop()
                logger.info("[Proactive] %s", "enabled" if enabled else "disabled")
            sw = getattr(self._runtime, "screen_watcher", None)
            if sw is not None:
                if enabled:
                    sw.start()
                else:
                    sw.stop()
        except Exception as e:
            logger.error("[Proactive] Error: %s", e)

    def set_proactive_idle(self, seconds: int) -> None:
        """Set the idle threshold before AI proactively speaks (seconds)."""
        try:
            ic = getattr(self._runtime, "initiative_checker", None)
            if ic is not None:
                ic.idle_threshold = max(15, min(3600, seconds))
                logger.info("[Proactive] Idle threshold set to %ds", ic.idle_threshold)
        except Exception as e:
            logger.error("[Proactive] Error setting idle threshold: %s", e)


# Module-level singleton for convenience
_manager: RuntimeManager | None = None


def get_manager() -> RuntimeManager:
    """Get or create the shared RuntimeManager instance."""
    global _manager
    if _manager is None:
        _manager = RuntimeManager()
    return _manager
