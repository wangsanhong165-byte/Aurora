import hashlib
import json
import sqlite3

import pytest

from scripts.migrate_runtime_data_v3 import migrate_runtime_data


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_fixture(root):
    memory = root / "data" / "memory" / "memory.db"
    memory.parent.mkdir(parents=True)
    with sqlite3.connect(memory) as conn:
        conn.execute("CREATE TABLE character_states (state_json TEXT NOT NULL)")
        conn.execute("CREATE TABLE retrieval_audit (result_json TEXT NOT NULL)")
        conn.execute("CREATE TABLE usage_events (context_json TEXT NOT NULL)")
        conn.execute(
            "INSERT INTO character_states VALUES (?)",
            (json.dumps({
                "tone": "happy",
                "nested": {"gesture": "wave"},
                "note": "tone and gesture are natural-language words",
            }),),
        )
        conn.execute(
            "INSERT INTO retrieval_audit VALUES (?)",
            (json.dumps([{"id": "memory-1", "tone": "relevant"}]),),
        )
        conn.execute("INSERT INTO usage_events VALUES ('{}')")

    turns = root / "data" / "runtime" / "turns.db"
    turns.parent.mkdir(parents=True)
    with sqlite3.connect(turns) as conn:
        conn.execute("CREATE TABLE turn_traces (detail_json TEXT NOT NULL)")
        conn.execute(
            "INSERT INTO turn_traces VALUES (?)",
            (json.dumps({
                "response": {
                    "segments": [{"text": "hello", "tone": "calm", "gesture": "nod"}],
                },
            }),),
        )

    histories = root / "data" / "memory" / "histories"
    histories.mkdir(parents=True)
    history = histories / "hist_demo.json"
    history.write_text(json.dumps([
        {"role": "user", "content": "keep tone and gesture exactly"},
        {"role": "assistant", "content": "unchanged"},
    ]), encoding="utf-8")
    return memory, turns, history


def test_dry_run_reports_changes_without_writing(tmp_path):
    memory, turns, history = create_fixture(tmp_path)
    before = {path: sha256(path) for path in (memory, turns, history)}

    report = migrate_runtime_data(tmp_path, apply=False)

    assert report["rowsChanged"] == 4
    assert report["historyArchives"] == 1
    assert {path: sha256(path) for path in before} == before
    assert not (tmp_path / "data" / "backups").exists()


def test_apply_backs_up_hashes_and_migrates_only_structured_keys(tmp_path):
    memory, turns, history = create_fixture(tmp_path)
    report = migrate_runtime_data(tmp_path, apply=True)

    assert report["rowsChanged"] == 4
    manifest_path = tmp_path / report["manifest"]
    manifest = json.loads(manifest_path.read_text("utf-8"))
    assert manifest["schemaVersion"] == 3
    assert len(manifest["files"]) == 2
    for item in manifest["files"]:
        backup = tmp_path / item["backup"]
        assert backup.exists()
        assert sha256(backup) == item["beforeSha256"]
        assert item["afterSha256"]

    with sqlite3.connect(memory) as conn:
        state = json.loads(conn.execute(
            "SELECT state_json FROM character_states"
        ).fetchone()[0])
    assert state["schemaVersion"] == 3
    assert state["emotion"] == "happy"
    assert state["nested"]["behavior"] == "wave"
    assert state["note"] == "tone and gesture are natural-language words"
    assert "tone" not in state
    assert "gesture" not in state["nested"]

    with sqlite3.connect(turns) as conn:
        detail = json.loads(conn.execute(
            "SELECT detail_json FROM turn_traces"
        ).fetchone()[0])
    assert detail["schemaVersion"] == 3
    assert detail["response"]["segments"][0]["emotion"] == "calm"
    assert detail["response"]["segments"][0]["behavior"] == "nod"

    with sqlite3.connect(memory) as conn:
        audit = json.loads(conn.execute(
            "SELECT result_json FROM retrieval_audit"
        ).fetchone()[0])
    assert audit == {
        "results": [{"emotion": "relevant", "id": "memory-1"}],
        "schemaVersion": 3,
    }

    archived = (
        tmp_path / "data" / "memory" / "histories"
        / "v2-archive" / history.name
    )
    assert archived.read_text("utf-8") == history.read_text("utf-8")


def test_second_apply_is_idempotent(tmp_path):
    create_fixture(tmp_path)
    first = migrate_runtime_data(tmp_path, apply=True)
    second = migrate_runtime_data(tmp_path, apply=True)

    assert first["rowsChanged"] == 4
    assert second["rowsChanged"] == 0
    assert second["historyArchives"] == 0
    assert second["manifest"] is None


def test_transaction_failure_keeps_original_database(tmp_path):
    memory, _, _ = create_fixture(tmp_path)
    before = sha256(memory)

    with pytest.raises(RuntimeError, match="injected migration failure"):
        migrate_runtime_data(tmp_path, apply=True, fail_after_updates=1)

    assert sha256(memory) == before
