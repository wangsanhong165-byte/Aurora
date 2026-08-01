from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "delegate_pi.py"


def load_module():
    spec = importlib.util.spec_from_file_location("delegate_pi", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load delegate_pi")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def delegate():
    return load_module()


def task_data() -> dict[str, object]:
    return {
        "task_id": "readme-smoke",
        "objective": "读取 README.md 并概括其职责，不修改文件。",
        "allowed_paths": ["README.md"],
        "acceptance_criteria": ["结果包含 README.md 的职责概括。"],
        "validation_commands": ["git diff --name-only"],
        "constraints": ["不得修改任何文件。"],
    }


def test_config_accepts_only_opencode_go_deepseek_v4_flash(delegate):
    config = delegate.default_config()

    assert config["engine"] == "pi"
    assert config["provider"] == "opencode-go"
    assert config["model"] == "deepseek-v4-flash"
    assert config["full_model"] == "opencode-go/deepseek-v4-flash"
    assert config["thinking"] == "max"
    assert "fallback" not in config
    assert "models" not in config

    for provider, model in [
        ("deepseek", "deepseek-v4-flash"),
        ("opencode-go", "deepseek-v4-pro"),
        ("opencode", "deepseek-v4-flash"),
    ]:
        broken = dict(config, provider=provider, model=model)
        with pytest.raises(delegate.DelegationError) as error:
            delegate.validate_config(broken)
        assert error.value.status == "wrong_model"


def test_init_checks_runtime_and_writes_fixed_config(delegate, tmp_path, monkeypatch):
    config_path = tmp_path / ".agent-router" / "config.json"

    monkeypatch.setattr(
        delegate,
        "check_runtime",
        lambda config, project_root: {
            "status": "success",
            "pi_version": "0.83.0",
            "full_model": "opencode-go/deepseek-v4-flash",
            "authenticated": True,
        },
    )

    result = delegate.init_router(config_path=config_path, project_root=tmp_path)
    saved = json.loads(config_path.read_text(encoding="utf-8"))

    assert result["status"] == "success"
    assert result["config_file"].endswith(".agent-router/config.json")
    assert saved["full_model"] == "opencode-go/deepseek-v4-flash"
    assert "api_key" not in saved


def test_disabled_router_refuses_new_delegations(delegate):
    config = delegate.default_config()
    config["enabled"] = False

    with pytest.raises(delegate.DelegationError) as error:
        delegate.ensure_enabled(config)

    assert error.value.status == "disabled"


def test_model_catalog_requires_exact_opencode_go_model_row(delegate):
    catalog = "\n".join(
        [
            "provider     model              context  max-out  thinking  images",
            "opencode-go  deepseek-v4-flash  1M       384K     yes       no",
            "opencode-go  deepseek-v4-pro    1M       384K     yes       no",
        ]
    )

    assert delegate.model_catalog_contains_fixed(catalog)
    assert not delegate.model_catalog_contains_fixed(
        "free-provider  deepseek-v4-flash  1M  384K  yes  no"
    )
    assert not delegate.model_catalog_contains_fixed(
        "opencode-go  deepseek-v4-flash-preview  1M  384K  yes  no"
    )


def test_load_task_rejects_missing_invalid_and_secret_content(delegate, tmp_path):
    with pytest.raises(delegate.DelegationError) as missing:
        delegate.load_task(tmp_path / "missing.json", tmp_path)
    assert missing.value.status == "invalid_task"

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{broken", encoding="utf-8")
    with pytest.raises(delegate.DelegationError) as invalid:
        delegate.load_task(invalid_path, tmp_path)
    assert invalid.value.status == "invalid_task"

    secret = task_data()
    secret["constraints"] = ["Authorization: Bearer top-secret-token"]
    secret_path = tmp_path / "secret.json"
    secret_path.write_text(json.dumps(secret, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(delegate.DelegationError) as leaked:
        delegate.load_task(secret_path, tmp_path)
    assert leaked.value.status == "invalid_task"

    broad = task_data()
    broad["allowed_paths"] = ["."]
    broad_path = tmp_path / "broad.json"
    broad_path.write_text(json.dumps(broad, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(delegate.DelegationError) as unrestricted:
        delegate.load_task(broad_path, tmp_path)
    assert unrestricted.value.status == "invalid_task"


def test_build_command_is_single_model_ephemeral_and_json(delegate, tmp_path):
    project_root = tmp_path / "project with spaces"
    project_root.mkdir()
    task_path = project_root / ".agent-runs" / "tasks" / "task.json"
    task_path.parent.mkdir(parents=True)
    task_path.write_text(json.dumps(task_data()), encoding="utf-8")

    command = delegate.build_pi_command(
        "C:\\Users\\Test User\\npm\\pi.cmd",
        delegate.default_config(),
        project_root,
        task_path,
        thinking="high",
    )

    assert command[0].endswith("pi.cmd")
    assert command[1:3] == ["--mode", "json"]
    assert "--print" in command
    assert "-p" not in command
    assert "--no-session" in command
    assert command[command.index("--provider") + 1] == "opencode-go"
    assert command[command.index("--model") + 1] == "deepseek-v4-flash"
    assert command[command.index("--thinking") + 1] == "high"
    assert "--models" not in command
    assert "--api-key" not in command
    assert "--no-extensions" in command
    assert "--no-skills" in command
    assert command[-1].startswith("你是由 Codex 委派的受限执行 Agent。")
    assert ".agent-runs/tasks/task.json" in command[-1]
    assert "\n" not in command[-1]
    assert len(command[-1]) < 1600


def test_thinking_level_is_bounded(delegate):
    assert delegate.validate_thinking("medium") == "medium"
    assert delegate.validate_thinking("xhigh") == "xhigh"
    with pytest.raises(delegate.DelegationError):
        delegate.validate_thinking("auto")


def test_task_timeout_can_only_tighten_global_timeout(delegate):
    config = delegate.default_config()

    assert delegate.effective_timeout({"timeout_seconds": 90}, config) == 90
    assert delegate.effective_timeout({"timeout_seconds": 3600}, config) == 1800
    assert delegate.effective_timeout({}, config) == 1800

    with pytest.raises(delegate.DelegationError) as error:
        delegate.effective_timeout({"timeout_seconds": 0}, config)
    assert error.value.status == "invalid_task"


def test_invoke_pi_times_out_without_retry(delegate, monkeypatch):
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        raise subprocess.TimeoutExpired(command, 1, output="partial", stderr="late")

    monkeypatch.setattr(delegate.subprocess, "run", fake_run)

    with pytest.raises(delegate.DelegationError) as error:
        delegate.invoke_pi(["pi", "--mode", "json", "task"], 1, Path.cwd())

    assert error.value.status == "timeout"
    assert len(calls) == 1


def test_dirty_workspace_is_refused_before_pi_starts(delegate, tmp_path, monkeypatch):
    task_path = tmp_path / ".agent-runs" / "tasks" / "dirty-guard.json"
    task_path.parent.mkdir(parents=True)
    task = task_data()
    task["task_id"] = "dirty-guard"
    task_path.write_text(json.dumps(task, ensure_ascii=False), encoding="utf-8")
    config_path = tmp_path / ".agent-router" / "config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps(delegate.default_config()), encoding="utf-8")

    monkeypatch.setattr(delegate, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(delegate, "LOG_PATH", tmp_path / "logs" / "delegations.jsonl")
    monkeypatch.setattr(delegate, "locate_pi", lambda config: "pi")
    monkeypatch.setattr(
        delegate,
        "snapshot_git",
        lambda project_root: delegate.GitSnapshot(True, {"existing.txt"}, {"existing.txt": "before"}),
    )
    started = False

    def unexpected_invoke(*args, **kwargs):
        nonlocal started
        started = True
        raise AssertionError("Pi must not start in a dirty workspace")

    monkeypatch.setattr(delegate, "invoke_pi", unexpected_invoke)

    result = delegate.run_task(
        task_path,
        allow_dirty=False,
        thinking=None,
        project_root=tmp_path,
    )

    assert result["status"] == "dirty_worktree"
    assert not started


def test_scope_check_accepts_directory_and_rejects_other_files(delegate):
    changed = ["src/feature/a.py", "README.md", "secrets.txt"]

    violations = delegate.find_scope_violations(changed, ["src/feature", "README.md"])

    assert violations == ["secrets.txt"]


def test_jsonl_and_usage_are_parsed_only_when_present(delegate):
    output = "\n".join(
        [
            json.dumps({"type": "session_start"}),
            json.dumps(
                {
                    "type": "message_update",
                    "message": {
                        "usage": {
                            "input": 999,
                            "output": 999,
                            "cacheRead": 999,
                            "cost": {"total": 999},
                        }
                    },
                }
            ),
            json.dumps(
                {
                    "type": "message_end",
                    "message": {
                        "usage": {
                            "input": 12,
                            "output": 5,
                            "cacheRead": 8,
                            "cost": {"input": 0.001, "total": 0.003},
                        }
                    },
                }
            ),
            json.dumps(
                {
                    "type": "message_end",
                    "message": {
                        "usage": {
                            "input": 4,
                            "output": 2,
                            "cacheRead": 0,
                            "cost": {"total": 0.001},
                        }
                    },
                }
            ),
        ]
    )

    events = delegate.parse_jsonl(output)
    usage = delegate.extract_usage(events)

    assert len(events) == 4
    assert usage == {
        "input_tokens": 16,
        "output_tokens": 7,
        "cache_tokens": 8,
        "cost": 0.004,
    }

    assert delegate.extract_usage([{"type": "session_start"}]) == {}


def test_invalid_json_output_is_explicit(delegate):
    with pytest.raises(delegate.DelegationError) as error:
        delegate.parse_jsonl("plain text")
    assert error.value.status == "invalid_json_output"


def test_redaction_removes_credentials(delegate):
    safe = delegate.redact_sensitive_text(
        'Authorization: Bearer abcdefghijklmnop OPENCODE_API_KEY=secret-value '
        '{"apiKey":"json-secret-value","token":"json-token-value"}'
    )
    assert "abcdefghijklmnop" not in safe
    assert "secret-value" not in safe
    assert "json-secret-value" not in safe
    assert "json-token-value" not in safe
    assert safe.count("[REDACTED]") >= 2


def test_stats_aggregates_lightweight_jsonl(delegate, tmp_path):
    log_path = tmp_path / "delegations.jsonl"
    entries = [
        {"task_id": "a", "status": "success", "duration_seconds": 2, "cost": 0.1},
        {"task_id": "b", "status": "timeout", "duration_seconds": 3},
        {"task_id": "c", "status": "scope_violation", "duration_seconds": 4},
    ]
    log_path.write_text(
        "".join(json.dumps(item) + "\n" for item in entries), encoding="utf-8"
    )

    stats = delegate.collect_stats(log_path)

    assert stats["total_calls"] == 3
    assert stats["successes"] == 1
    assert stats["failures"] == 2
    assert stats["timeouts"] == 1
    assert stats["scope_violations"] == 1
    assert stats["duration_seconds"] == 9
    assert stats["cost"] == 0.1
