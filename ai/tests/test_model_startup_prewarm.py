"""Regression guards for eager GPU model startup."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_asr_startup_loads_the_model_not_only_the_adapter():
    api = (ROOT / "app/modules/asr/api.py").read_text(encoding="utf-8")
    engine = (ROOT / "app/modules/asr/engines/qwen.py").read_text(encoding="utf-8")

    assert "def preload(" in engine
    assert "_engine.preload()" in api
    assert '_engine_ready = True' in api


def test_tts_exposes_real_synthesis_warmup_and_ready_state():
    api = (ROOT / "app/modules/tts/api.py").read_text(encoding="utf-8")

    assert '@app.post("/warmup")' in api
    assert "_engine_warm = True" in api
    assert '"warm": _engine_warm' in api


def test_manifest_declares_gpu_service_dependency_order():
    import json
    manifest = json.loads((ROOT / "config/services.json").read_text(encoding="utf-8"))
    assert manifest["tts"]["depends_on"] == ["gsvi"]
    assert "warmup" in manifest["tts"]
    assert manifest["asr"]["depends_on"] == ["tts"]
    assert manifest["gsvi"]["readiness"] is True


def test_python_supervisor_owns_lifecycle_core():
    supervisor = (ROOT / "app/lifecycle/supervisor.py").read_text(encoding="utf-8")
    assert "LifecycleOrchestrator" in supervisor
    assert "ControlServer" in supervisor


def test_soulctl_is_the_entry_and_electron_main_owns_its_launch_shutdown():
    entry = (ROOT / "soulctl.cmd").read_text(encoding="utf-8")
    main = (ROOT / "frontend/electron/main.cjs").read_text(encoding="utf-8")

    assert "scripts\\soulctl.cjs" in entry
    assert "electron.pid" in main
    assert "taskkill" not in entry
    assert "shutdownStarted" in main


def test_process_manager_is_a_thin_supervisor_adapter():
    manager = (ROOT / "electron/process-manager.cjs").read_text(encoding="utf-8")
    assert "app.lifecycle.client" in manager
    assert "SERVICE_DEFINITIONS" not in manager
    assert "taskkill" not in manager
    assert "netstat" not in manager


def test_run_py_is_only_a_thin_lifecycle_client():
    launcher = (ROOT / "run.py").read_text(encoding="utf-8")

    assert 'get("availability") == "FULL_READY"' in launcher
    assert "procs, log_files" not in launcher
    assert "for p in procs" not in launcher
    assert "for f in log_files" not in launcher
    assert "TTS was loaded before ASR startup" not in launcher
