from app.runtime.tool_settings import ToolSettingsStore


def test_tool_settings_persist_enablement(tmp_path):
    path = tmp_path / "tools.json"
    settings = ToolSettingsStore(path)
    assert settings.is_enabled("clock") is True
    settings.set_enabled("clock", False)
    assert settings.is_enabled("clock") is False
    assert ToolSettingsStore(path).is_enabled("clock") is False
