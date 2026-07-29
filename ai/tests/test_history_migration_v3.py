import json

from scripts.migrate_runtime_data_v3 import migrate_runtime_data


def test_history_archive_is_lossless_and_not_imported_at_runtime(tmp_path):
    histories = tmp_path / "data" / "memory" / "histories"
    histories.mkdir(parents=True)
    source = histories / "hist_demo.json"
    source.write_text(json.dumps([
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]), encoding="utf-8")

    first = migrate_runtime_data(tmp_path, apply=True)
    second = migrate_runtime_data(tmp_path, apply=True)

    assert first["historyArchives"] == 1
    assert second["historyArchives"] == 0
    assert source.exists()
    archive = histories / "v2-archive" / source.name
    assert archive.read_bytes() == source.read_bytes()
