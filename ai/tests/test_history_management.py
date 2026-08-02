import json
import os
import errno
import pytest

from app.runtime.management import RuntimeManager


class _Conversation:
    def clear(self):
        pass


class _Runtime:
    providers = {}
    conversation = _Conversation()

    def get_character_info(self):
        return {"card": {"id": "monika"}}


def test_history_index_persists_delete_atomically(tmp_path, monkeypatch):
    manager = RuntimeManager(base_dir=tmp_path, runtime=_Runtime())
    created = manager.create_history()
    history_uid = created["history_uid"]
    history_path = manager._histories_dir / f"{history_uid}.json"
    history_path.write_text("[]", encoding="utf-8")

    replace_calls = []
    real_replace = os.replace

    def track_replace(source, target):
        replace_calls.append((source, target))
        return real_replace(source, target)

    monkeypatch.setattr(os, "replace", track_replace)

    result = manager.delete_history(history_uid)

    assert result == {"success": True, "history_uid": history_uid}
    assert not history_path.exists()
    assert history_uid not in json.loads(
        (manager._histories_dir / "index.json").read_text(encoding="utf-8")
    )
    assert replace_calls


def test_history_index_recovers_existing_history_files(tmp_path):
    histories_dir = tmp_path / "data" / "memory" / "histories"
    histories_dir.mkdir(parents=True)
    (histories_dir / "index.json").write_text(
        json.dumps({
            "hist_known": {
                "timestamp": "2026-08-02T00:00:00+00:00",
                "latest_message": "known",
            }
        }),
        encoding="utf-8",
    )
    (histories_dir / "hist_known.json").write_text("[]", encoding="utf-8")
    (histories_dir / "hist_orphan.json").write_text(
        json.dumps([
            {"role": "user", "content": "找回这条记录"},
            {"role": "assistant", "content": "还在"},
        ]),
        encoding="utf-8",
    )
    (histories_dir / "hist_invalid.json").write_text("not json", encoding="utf-8")

    manager = RuntimeManager(base_dir=tmp_path, runtime=_Runtime())

    entries = {entry["uid"]: entry for entry in manager.get_history_list()}
    assert entries["hist_known"]["latest_message"] == "known"
    assert entries["hist_orphan"]["latest_message"] == "找回这条记录"
    assert "hist_invalid" not in entries
    persisted = json.loads((histories_dir / "index.json").read_text(encoding="utf-8"))
    assert "hist_orphan" in persisted


def test_history_index_write_failure_preserves_previous_index(tmp_path, monkeypatch):
    manager = RuntimeManager(base_dir=tmp_path, runtime=_Runtime())
    created = manager.create_history()
    index_path = manager._histories_dir / "index.json"
    previous = index_path.read_text(encoding="utf-8")

    def fail_replace(source, target):
        raise OSError(errno.EINVAL, "simulated replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)

    manager._history_index[created["history_uid"]] = {
        "timestamp": "2026-08-02T00:00:00+00:00",
        "latest_message": "updated",
    }
    try:
        manager._save_index()
    except OSError:
        pass
    else:
        raise AssertionError("expected the simulated index write to fail")

    assert index_path.read_text(encoding="utf-8") == previous


def test_delete_history_restores_json_when_index_write_fails(tmp_path, monkeypatch):
    manager = RuntimeManager(base_dir=tmp_path, runtime=_Runtime())
    history_uid = manager.create_history()["history_uid"]
    history_path = manager._histories_dir / f"{history_uid}.json"
    history_path.write_text(
        json.dumps([{"role": "user", "content": "保留这条"}]),
        encoding="utf-8",
    )
    previous_index = (manager._histories_dir / "index.json").read_text(
        encoding="utf-8"
    )

    def fail_replace(source, target):
        raise OSError(errno.EINVAL, "simulated replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError):
        manager.delete_history(history_uid)

    assert history_path.exists()
    assert (manager._histories_dir / "index.json").read_text(
        encoding="utf-8"
    ) == previous_index
    assert history_uid in {entry["uid"] for entry in manager.get_history_list()}
