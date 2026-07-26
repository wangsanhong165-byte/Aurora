"""Lossless import of pre-V3 JSON histories into idempotent SQLite turns."""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
from pathlib import Path
from typing import Any


def migrate_legacy_histories(
    base_dir: Path,
    store: Any,
    *,
    character_id: str,
) -> int:
    histories_dir = base_dir / "data" / "memory" / "histories"
    if not histories_dir.exists():
        return 0
    archive_dir = histories_dir / "v2-archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    migrated_files = 0

    for source in sorted(histories_dir.glob("hist_*.json")):
        try:
            messages = json.loads(source.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(messages, list):
            continue

        file_inserted = False
        pending_user = ""
        pair_index = 0
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role", ""))
            content = str(message.get("content", ""))
            if role == "user":
                pending_user = content
                continue
            if role != "assistant" or not content:
                continue
            identity = f"{source.stem}:{pair_index}:{pending_user}:{content}"
            turn_id = "legacy-" + hashlib.sha256(
                identity.encode("utf-8")
            ).hexdigest()[:24]
            inserted = store.log_turn(
                pending_user,
                {"reply_text": content, "intent": "legacy_import"},
                character_id=character_id,
                turn_id=turn_id,
                write_token="legacy_history_import",
                history_uid=source.stem,
            )
            file_inserted = inserted or file_inserted
            pair_index += 1
            pending_user = ""

        archive = archive_dir / source.name
        if not archive.exists():
            shutil.copy2(source, archive)
            archive.chmod(stat.S_IREAD)
        if file_inserted:
            migrated_files += 1

    return migrated_files
