import json
from pathlib import Path

from scripts.launcher import LauncherConfig, choose_python, profile_command


def test_local_runtime_config_wins_over_path_python(tmp_path: Path):
    configured = tmp_path / "python.exe"
    configured.write_text("", encoding="utf-8")
    config = tmp_path / "runtime.local.json"
    config.write_text(json.dumps({"python": str(configured)}), encoding="utf-8")

    assert choose_python(config, {"PATH": "ignored"}) == configured


def test_main_python_environment_wins_over_local_config(tmp_path: Path):
    environment_python = tmp_path / "env-python.exe"
    environment_python.write_text("", encoding="utf-8")
    configured = tmp_path / "configured.exe"
    configured.write_text("", encoding="utf-8")
    config = tmp_path / "runtime.local.json"
    config.write_text(json.dumps({"python": str(configured)}), encoding="utf-8")

    assert choose_python(config, {"MAIN_PYTHON": str(environment_python)}) == environment_python


def test_web_profile_uses_backend_services_without_vite():
    config = LauncherConfig(root=Path("C:/project"), python=Path("python.exe"))
    command = profile_command(config, "web")
    assert command[-3:] == ["start", "--mode", "backend"]


def test_electron_profile_passes_selected_python_to_electron():
    config = LauncherConfig(root=Path("C:/project"), python=Path("C:/env/python.exe"))
    command = profile_command(config, "electron")
    assert command[-2:] == ["run", "electron:start"]


def test_batch_files_share_one_python_bootstrap():
    root = Path(__file__).resolve().parents[1]
    web = (root / "start_web.bat").read_text(encoding="utf-8")
    electron = (root / "start_electron.bat").read_text(encoding="utf-8")
    bootstrap = (root / "scripts/launch.cmd").read_text(encoding="utf-8")
    assert "call scripts\\launch.cmd web" in web
    assert "call scripts\\launch.cmd electron" in electron
    assert "qwen3-asr\\python.exe" in bootstrap
