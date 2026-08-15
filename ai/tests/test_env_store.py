"""env_store: read/write config/.env for the settings UI."""

import app.config_manager.env_store as env_store


def test_read_exposed_keys(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "LLM_ENGINE=deepseek\n"
        "LLM_BASE_URL=https://api.deepseek.com\n"
        "DEEPSEEK_API_KEY=sk-test\n"
        "ASR_ENGINE=qwen3-asr\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(env_store, "_ENV_PATH", env)

    vals = env_store.read_env_values()

    assert vals["llm"]["LLM_ENGINE"] == "deepseek"
    assert vals["llm"]["DEEPSEEK_API_KEY"] == "sk-test"
    assert vals["llm"]["LLM_BASE_URL"] == "https://api.deepseek.com"
    assert vals["asr"]["ASR_ENGINE"] == "qwen3-asr"
    # Missing keys come back empty rather than raising.
    assert vals["llm"]["OPENAI_API_KEY"] == ""


def test_write_updates_and_preserves_comments(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# header comment\n"
        "LLM_ENGINE=deepseek # deepseek | openai | local\n"
        "TTS_ENGINE=gsvi-v2pro\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(env_store, "_ENV_PATH", env)

    env_store.write_env_values({
        "llm": {"LLM_ENGINE": "openai", "LLM_MODEL": "gpt-4o"},
    })

    text = env.read_text(encoding="utf-8")
    # Inline comment preserved, value updated.
    assert "LLM_ENGINE=openai # deepseek | openai | local" in text
    # New key appended.
    assert "LLM_MODEL=gpt-4o" in text
    # Untouched keys preserved.
    assert "TTS_ENGINE=gsvi-v2pro" in text
    assert "# header comment" in text


def test_write_rejects_unknown_group_keys(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("TTS_ENGINE=gsvi-v2pro\n", encoding="utf-8")
    monkeypatch.setattr(env_store, "_ENV_PATH", env)

    # A key outside the exposed set must not be written.
    env_store.write_env_values({"llm": {"ACTIVE_CHARACTER": "hacked"}})

    assert "ACTIVE_CHARACTER" not in env.read_text(encoding="utf-8")
    assert "TTS_ENGINE=gsvi-v2pro" in env.read_text(encoding="utf-8")


def test_env_store_exposes_opencode_keys():
    assert "OPENCODE_API_KEY" in env_store.EXPOSED_KEYS["llm"]
    assert "OPENCODE_BASE_URL" in env_store.EXPOSED_KEYS["llm"]
    assert "OPENCODE_MODEL" in env_store.EXPOSED_KEYS["llm"]


def test_env_store_roundtrips_opencode_values(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    monkeypatch.setattr(env_store, "_ENV_PATH", env)

    env_store.write_env_values({
        "llm": {
            "OPENCODE_BASE_URL": "http://127.0.0.1:4096/v1",
            "OPENCODE_MODEL": "opencode",
            "OPENCODE_API_KEY": "local",
        }
    })
    vals = env_store.read_env_values()
    assert vals["llm"]["OPENCODE_BASE_URL"] == "http://127.0.0.1:4096/v1"
    assert vals["llm"]["OPENCODE_MODEL"] == "opencode"
    assert vals["llm"]["OPENCODE_API_KEY"] == "local"


def test_config_manager_has_opencode_engine():
    from app.config_manager.llm import LLMConfig, OpenCodeConfig
    from app.config_manager import OpenCodeConfig as Exported

    cfg = LLMConfig()
    assert cfg.opencode.engine == "opencode"
    assert cfg.opencode.base_url == "http://127.0.0.1:4096/v1"
    assert cfg.opencode.model == "opencode"
    assert Exported is OpenCodeConfig
