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


def test_electron_starts_gpu_services_in_dependency_order():
    manager = (ROOT / "electron/process-manager.cjs").read_text(encoding="utf-8")

    gsvi = manager.index("await this._startAndWait('gsvi')")
    tts = manager.index("await this._startAndWait('tts')")
    warmup = manager.index("await this._warmupTTS()")
    asr = manager.index("await this._startAndWait('asr')")
    assert gsvi < tts < warmup < asr
    assert "payload.ready === false" in manager


def test_python_lifecycle_uses_model_ready_checks_and_tts_warmup():
    lifecycle = (ROOT / "scripts/lifecycle.py").read_text(encoding="utf-8")

    assert "require_ready" in lifecycle
    assert "warmup_tts" in lifecycle
    assert "/warmup" in lifecycle


def test_electron_bat_replaces_only_the_previous_companion_instance():
    bat = (ROOT / "start_electron.bat").read_text(encoding="utf-8")
    main = (ROOT / "frontend/electron/main.cjs").read_text(encoding="utf-8")

    assert "electron.pid" in bat
    assert "electron.pid" in main
    assert "taskkill /F /T /PID" in bat
    assert "taskkill /IM electron.exe" not in bat
