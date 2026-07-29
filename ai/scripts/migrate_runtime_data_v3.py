"""One-time migration of persisted runtime JSON from the V2 field schema to V3.

This script is deliberately outside the production startup path.  Run it once
with ``--dry-run`` first, stop the desktop runtime, then run it with ``--apply``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 3


@dataclass(frozen=True)
class JsonColumn:
    database: Path
    table: str
    column: str
    list_wrapper: str | None = None


JSON_COLUMNS = (
    JsonColumn(Path("data/memory/memory.db"), "character_states", "state_json"),
    JsonColumn(
        Path("data/memory/memory.db"),
        "retrieval_audit",
        "result_json",
        "results",
    ),
    JsonColumn(Path("data/memory/memory.db"), "usage_events", "context_json"),
    JsonColumn(Path("data/runtime/turns.db"), "turn_traces", "detail_json"),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _transform(value: Any) -> tuple[Any, int]:
    """Rename structured keys without rewriting natural-language string values."""
    if isinstance(value, list):
        renamed = 0
        transformed = []
        for item in value:
            migrated, count = _transform(item)
            transformed.append(migrated)
            renamed += count
        return transformed, renamed

    if not isinstance(value, dict):
        return value, 0

    transformed: dict[str, Any] = {}
    renamed = 0
    for key, item in value.items():
        migrated, count = _transform(item)
        renamed += count
        if key == "tone":
            if "emotion" not in value:
                transformed["emotion"] = migrated
            renamed += 1
            continue
        if key == "gesture":
            if "behavior" not in value:
                transformed["behavior"] = migrated
            renamed += 1
            continue
        transformed[key] = migrated

    return transformed, renamed


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return any(row[1] == column for row in rows)


def _scan_database(
    database: Path,
    columns: list[JsonColumn],
) -> tuple[list[tuple[str, str, int, str]], int, list[str]]:
    updates: list[tuple[str, str, int, str]] = []
    renamed = 0
    errors: list[str] = []
    with closing(sqlite3.connect(database)) as conn:
        for target in columns:
            if not _table_has_column(conn, target.table, target.column):
                continue
            rows = conn.execute(
                f'SELECT rowid, "{target.column}" FROM "{target.table}"'
            ).fetchall()
            for rowid, raw in rows:
                if raw is None or raw == "":
                    continue
                try:
                    parsed = json.loads(raw)
                except (TypeError, json.JSONDecodeError) as exc:
                    errors.append(
                        f"{target.database.as_posix()}:{target.table}"
                        f"[rowid={rowid}].{target.column}: {exc}"
                    )
                    continue
                if isinstance(parsed, list) and target.list_wrapper:
                    parsed = {
                        "schemaVersion": SCHEMA_VERSION,
                        target.list_wrapper: parsed,
                    }
                elif not isinstance(parsed, dict):
                    errors.append(
                        f"{target.database.as_posix()}:{target.table}"
                        f"[rowid={rowid}].{target.column}: root must be an object"
                    )
                    continue
                migrated, count = _transform(parsed)
                migrated["schemaVersion"] = SCHEMA_VERSION
                encoded = json.dumps(
                    migrated,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                if encoded != raw:
                    updates.append(
                        (target.table, target.column, int(rowid), encoded)
                    )
                    renamed += count
    return updates, renamed, errors


def _sqlite_snapshot(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source)) as source_conn:
        with closing(sqlite3.connect(destination)) as destination_conn:
            source_conn.backup(destination_conn)


def _migrate_database(
    source: Path,
    backup: Path,
    updates: list[tuple[str, str, int, str]],
    *,
    fail_after_updates: int | None,
) -> tuple[dict[str, Any], int | None]:
    _sqlite_snapshot(source, backup)
    before_sha = _sha256(backup)

    applied = 0
    with closing(sqlite3.connect(source, timeout=5.0)) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            for table, column, rowid, encoded in updates:
                conn.execute(
                    f'UPDATE "{table}" SET "{column}" = ? WHERE rowid = ?',
                    (encoded, rowid),
                )
                applied += 1
                if (
                    fail_after_updates is not None
                    and applied >= fail_after_updates
                ):
                    raise RuntimeError("injected migration failure")
            conn.commit()
            integrity = conn.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise RuntimeError(f"SQLite integrity check failed: {integrity}")
        except Exception:
            conn.rollback()
            raise

    return {
        "original": None,
        "backup": None,
        "beforeSha256": before_sha,
        "afterSha256": _sha256(source),
        "rowsChanged": applied,
    }, (
        None
        if fail_after_updates is None
        else fail_after_updates - applied
    )


def _history_sources(root: Path) -> list[tuple[Path, Path]]:
    histories = root / "data" / "memory" / "histories"
    archive = histories / "v2-archive"
    if not histories.exists():
        return []
    pending = []
    for source in sorted(histories.glob("hist_*.json")):
        destination = archive / source.name
        if not destination.exists() or _sha256(source) != _sha256(destination):
            pending.append((source, destination))
    return pending


def migrate_runtime_data(
    root: Path,
    *,
    apply: bool,
    fail_after_updates: int | None = None,
) -> dict[str, Any]:
    root = Path(root).resolve()
    grouped: dict[Path, list[JsonColumn]] = {}
    for target in JSON_COLUMNS:
        grouped.setdefault(target.database, []).append(target)

    scans: dict[Path, list[tuple[str, str, int, str]]] = {}
    renamed = 0
    errors: list[str] = []
    for relative_database, columns in grouped.items():
        database = root / relative_database
        if not database.exists():
            continue
        updates, key_count, database_errors = _scan_database(database, columns)
        scans[relative_database] = updates
        renamed += key_count
        errors.extend(database_errors)

    history_sources = _history_sources(root)
    report: dict[str, Any] = {
        "mode": "apply" if apply else "dry-run",
        "schemaVersion": SCHEMA_VERSION,
        "rowsChanged": sum(len(updates) for updates in scans.values()),
        "legacyKeysMigrated": renamed,
        "historyArchives": len(history_sources),
        "validationErrors": errors,
        "manifest": None,
    }
    if errors:
        if apply:
            raise ValueError(
                "Migration refused because persisted JSON validation failed:\n"
                + "\n".join(errors)
            )
        return report
    if not apply or (report["rowsChanged"] == 0 and not history_sources):
        return report

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup_root = root / "data" / "backups" / "v3-protocol" / stamp
    backup_root.mkdir(parents=True, exist_ok=False)

    files: list[dict[str, Any]] = []
    remaining_failure = fail_after_updates
    for relative_database, updates in scans.items():
        if not updates:
            continue
        source = root / relative_database
        backup = backup_root / relative_database
        item, remaining_failure = _migrate_database(
            source,
            backup,
            updates,
            fail_after_updates=remaining_failure,
        )
        item["original"] = _relative(source, root)
        item["backup"] = _relative(backup, root)
        files.append(item)

    for source, destination in history_sources:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if _sha256(source) != _sha256(destination):
            raise RuntimeError(f"History archive verification failed: {source}")

    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "files": files,
        "historyArchives": [
            {
                "source": _relative(source, root),
                "archive": _relative(destination, root),
                "sha256": _sha256(source),
            }
            for source, destination in history_sources
        ],
    }
    manifest_path = backup_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report["manifest"] = _relative(manifest_path, root)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Project root (defaults to the repository containing this script)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the migration. Without this flag, only a dry-run is performed.",
    )
    args = parser.parse_args()
    report = migrate_runtime_data(args.root, apply=args.apply)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
