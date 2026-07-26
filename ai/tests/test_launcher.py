from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_soulctl_is_the_only_windows_source_launcher():
    entry = (ROOT / "soulctl.cmd").read_text(encoding="utf-8")
    assert "scripts\\soulctl.cjs" in entry
    assert "scripts\\launcher.py" not in entry
    assert not (ROOT / "start_web.bat").exists()
    assert not (ROOT / "start_electron.bat").exists()
    assert not (ROOT / "scripts/launch.cmd").exists()
    assert not (ROOT / "scripts/launcher.py").exists()


def test_node_controller_does_not_define_service_lifecycle_rules():
    controller = (ROOT / "scripts/soulctl.cjs").read_text(encoding="utf-8")
    assert "app.lifecycle.client" in controller
    assert "depends_on" not in controller
    assert "readiness" not in controller
    assert "taskkill" not in controller
