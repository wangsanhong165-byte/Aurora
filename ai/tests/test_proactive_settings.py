"""Proactive switch + idle gate read from persisted settings."""

from app.runtime.runtime import CharacterRuntime


def _rt():
    # Build an instance WITHOUT running __init__ (no service startup).
    return CharacterRuntime.__new__(CharacterRuntime)


def test_load_proactive_settings_defaults(tmp_path):
    proactive, idle = _rt()._load_proactive_settings(tmp_path / "missing.json")
    assert proactive is True
    assert idle is None


def test_load_proactive_settings_reads_values(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        '{"proactive": false, "proactiveIdleTime": 180}', encoding="utf-8"
    )
    proactive, idle = _rt()._load_proactive_settings(settings)
    assert proactive is False
    assert idle == 180.0


def test_load_proactive_settings_ignores_small_idle(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        '{"proactive": true, "proactiveIdleTime": 5}', encoding="utf-8"
    )
    proactive, idle = _rt()._load_proactive_settings(settings)
    assert proactive is True
    assert idle is None  # <10s is treated as "not configured"


def test_load_proactive_settings_tolerates_malformed(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text("not json", encoding="utf-8")
    proactive, idle = _rt()._load_proactive_settings(settings)
    assert proactive is True
    assert idle is None
