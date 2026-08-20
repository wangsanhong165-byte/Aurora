#!/usr/bin/env python3
"""Thin 主 Agent -> Pi -> OpenCode Go -> DeepSeek V4 Flash delegation layer."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / ".agent-router" / "config.json"
RUN_ROOT = PROJECT_ROOT / ".agent-runs"
LOG_PATH = RUN_ROOT / "logs" / "delegations.jsonl"
RESULTS_DIR = RUN_ROOT / "results"

FIXED_PROVIDER = "opencode-go"
FIXED_MODEL = "deepseek-v4-flash"
THINKING_LEVELS = {"max"}  # 质量优先：固定 max，禁止降档
TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SENSITIVE_PATTERN = re.compile(
    r"(?i)(authorization\s*:\s*bearer\s+)([^\s\"',}]+)"
    r"|([\"']?(?:api[_-]?key|token|cookie|password|secret)[\"']?\s*[=:]\s*[\"']?)([^\s\"',}]+)"
    r"|(sk-[A-Za-z0-9_-]{8})([A-Za-z0-9_-]+)"
)


class DelegationError(RuntimeError):
    def __init__(
        self,
        status: str,
        message: str,
        *,
        stdout: str = "",
        stderr: str = "",
        exit_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code


@dataclass(frozen=True)
class GitSnapshot:
    dirty: bool
    paths: set[str]
    fingerprints: dict[str, str]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_config() -> dict[str, Any]:
    return {
        "enabled": True,
        "engine": "pi",
        "provider": FIXED_PROVIDER,
        "model": FIXED_MODEL,
        "full_model": f"{FIXED_PROVIDER}/{FIXED_MODEL}",
        "thinking": "max",
        "timeout_seconds": 1800,
        "tools": ["read", "bash", "edit", "write", "grep", "find", "ls"],
        "enable_local_usage_log": True,
        "pi_command": "pi",
    }


def validate_thinking(value: str) -> str:
    if value not in THINKING_LEVELS:
        raise DelegationError(
            "invalid_task",
            f"为保障代码质量，thinking 固定为 max，禁止降档（收到：{value}）；允许值：{sorted(THINKING_LEVELS)}",
        )
    return value


def effective_timeout(task: dict[str, Any], config: dict[str, Any]) -> int:
    global_timeout = config["timeout_seconds"]
    task_timeout = task.get("timeout_seconds", global_timeout)
    if (
        not isinstance(task_timeout, int)
        or isinstance(task_timeout, bool)
        or task_timeout <= 0
    ):
        raise DelegationError("invalid_task", "timeout_seconds 必须是正整数。")
    return min(global_timeout, task_timeout)


def model_catalog_contains_fixed(output: str) -> bool:
    """Return true only for an exact provider/model row from Pi's model table."""
    for line in output.splitlines():
        columns = line.strip().split()
        if len(columns) >= 2 and columns[0] == FIXED_PROVIDER and columns[1] == FIXED_MODEL:
            return True
    return False


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(config.get("enabled", True), bool):
        raise DelegationError("invalid_task", "enabled 必须是布尔值。")
    if config.get("engine") != "pi":
        raise DelegationError("wrong_model", "执行器必须固定为 Pi。")
    if (
        config.get("provider") != FIXED_PROVIDER
        or config.get("model") != FIXED_MODEL
        or config.get("full_model") != f"{FIXED_PROVIDER}/{FIXED_MODEL}"
    ):
        raise DelegationError(
            "wrong_model",
            f"只允许 {FIXED_PROVIDER}/{FIXED_MODEL}，禁止其他模型或 provider。",
        )
    forbidden_keys = {"fallback", "fallbacks", "models", "candidate_models", "api_key"}
    present = sorted(forbidden_keys.intersection(config))
    if present:
        raise DelegationError("wrong_model", f"配置包含被禁止的多模型或凭据字段：{present}")
    validate_thinking(str(config.get("thinking", "medium")))
    timeout = config.get("timeout_seconds")
    if not isinstance(timeout, int) or timeout <= 0:
        raise DelegationError("invalid_task", "timeout_seconds 必须是正整数。")
    tools = config.get("tools")
    if not isinstance(tools, list) or not tools or not all(isinstance(item, str) for item in tools):
        raise DelegationError("invalid_task", "tools 必须是非空字符串列表。")
    return config


def ensure_enabled(config: dict[str, Any]) -> None:
    if not config.get("enabled", True):
        raise DelegationError("disabled", "Pi 委派已在 .agent-router/config.json 中禁用。")


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DelegationError("invalid_task", f"缺少配置文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise DelegationError("invalid_task", f"配置文件不是有效 JSON：{exc}") from exc
    if not isinstance(config, dict):
        raise DelegationError("invalid_task", "配置文件根节点必须是对象。")
    return validate_config(config)


def _normalise_relative_path(value: str, project_root: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DelegationError("invalid_task", "allowed_paths 中存在空路径。")
    candidate = value.replace("\\", "/").strip()
    pure = PurePosixPath(candidate)
    if candidate in {"", "."}:
        raise DelegationError("invalid_task", "allowed_paths 不允许使用整个项目根目录。")
    if pure.is_absolute() or ".." in pure.parts:
        raise DelegationError("invalid_task", f"路径必须位于项目内：{value}")
    resolved = (project_root / Path(*pure.parts)).resolve()
    try:
        resolved.relative_to(project_root.resolve())
    except ValueError as exc:
        raise DelegationError("invalid_task", f"路径越出项目根目录：{value}") from exc
    return pure.as_posix().rstrip("/") or "."


def _contains_secret(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False)
    return bool(SENSITIVE_PATTERN.search(text))


def load_task(path: Path, project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    path = path.resolve()
    try:
        path.relative_to(project_root.resolve())
    except ValueError as exc:
        raise DelegationError("invalid_task", "任务文件必须位于项目目录内。") from exc
    try:
        task = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DelegationError("invalid_task", f"任务文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise DelegationError("invalid_task", f"任务文件不是有效 JSON：{exc}") from exc
    if not isinstance(task, dict):
        raise DelegationError("invalid_task", "任务文件根节点必须是对象。")
    required_lists = ("allowed_paths", "acceptance_criteria", "validation_commands", "constraints")
    task_id = task.get("task_id")
    objective = task.get("objective")
    if not isinstance(task_id, str) or not TASK_ID_PATTERN.fullmatch(task_id):
        raise DelegationError("invalid_task", "task_id 只能包含字母、数字、点、下划线和连字符。")
    if not isinstance(objective, str) or len(objective.strip()) < 8:
        raise DelegationError("invalid_task", "objective 必须是具体、非空且可验收的目标。")
    for key in required_lists:
        value = task.get(key)
        if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
            raise DelegationError("invalid_task", f"{key} 必须是非空字符串列表。")
    task["allowed_paths"] = [
        _normalise_relative_path(item, project_root) for item in task["allowed_paths"]
    ]
    if _contains_secret(task):
        raise DelegationError("invalid_task", "任务文件疑似包含凭据、Token 或其他秘密。")
    return task


def locate_pi(config: dict[str, Any]) -> str:
    configured = str(config.get("pi_command", "pi"))
    configured_path = Path(configured)
    if configured_path.is_absolute() and configured_path.exists():
        return str(configured_path)
    found = shutil.which(configured) or shutil.which("pi.cmd") or shutil.which("pi")
    if found:
        return found
    candidates: list[Path] = []
    if os.environ.get("APPDATA"):
        candidates.append(Path(os.environ["APPDATA"]) / "npm" / "pi.cmd")
    candidates.extend(
        [
            Path.home() / "AppData" / "Roaming" / "npm" / "pi.cmd",
            Path.home() / ".local" / "bin" / "pi",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    raise DelegationError(
        "pi_not_found",
        "未找到 Pi CLI。安装：npm install -g --ignore-scripts @earendil-works/pi-coding-agent",
    )


def build_pi_command(
    executable: str,
    config: dict[str, Any],
    project_root: Path,
    task_path: Path,
    *,
    thinking: str | None = None,
) -> list[str]:
    validate_config(config)
    chosen_thinking = validate_thinking(thinking or str(config["thinking"]))
    relative_task = task_path.resolve().relative_to(project_root.resolve()).as_posix()
    prompt = f"""你是由主 Agent 委派的受限执行 Agent。

读取任务规范文件 {relative_task} 并完成其中目标。

规则：
1. 修改前调查相关代码，只完成任务目标。
2. 只修改 allowed_paths；不得读取或输出无关密钥。
3. 禁止 git commit、push、merge、reset、checkout、clean 或修改 remote。
4. 禁止调用其他 Agent、模型或外部编码 CLI。
5. 禁止删除、跳过、弱化测试，禁止占位实现、假数据或吞异常。
6. 必须执行 validation_commands，失败时如实报告。
7. 最后报告调查、修改文件、实现、验证结果、未解决问题和风险。
"""
    # Windows .cmd shims can truncate a quoted argument at the first newline.
    # The complete task remains in JSON; keep only this short pointer prompt on one line.
    prompt = " ".join(prompt.split())
    return [
        executable,
        "--mode",
        "json",
        "--print",
        "--no-session",
        "--approve",
        "--provider",
        FIXED_PROVIDER,
        "--model",
        FIXED_MODEL,
        "--thinking",
        chosen_thinking,
        "--tools",
        ",".join(config["tools"]),
        "--no-extensions",
        "--no-skills",
        "--no-prompt-templates",
        prompt,
    ]


def invoke_pi(command: list[str], timeout_seconds: int, cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=str(cwd),
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        raise DelegationError(
            "timeout",
            f"Pi 调用超过 {timeout_seconds} 秒，已终止；未自动重试。",
            stdout=stdout,
            stderr=stderr,
        ) from exc


def redact_sensitive_text(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        prefix = match.group(1) or match.group(3) or match.group(5) or ""
        return f"{prefix}[REDACTED]"

    return SENSITIVE_PATTERN.sub(replace, text)


def parse_jsonl(output: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for number, line in enumerate(output.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DelegationError(
                "invalid_json_output", f"Pi 第 {number} 行不是有效 JSON；原始输出已保留。"
            ) from exc
        if not isinstance(event, dict):
            raise DelegationError("invalid_json_output", f"Pi 第 {number} 行不是 JSON 对象。")
        events.append(event)
    if not events:
        raise DelegationError("invalid_json_output", "Pi 没有返回 JSON 事件。")
    return events


def extract_usage(events: list[dict[str, Any]]) -> dict[str, int | float]:
    totals: dict[str, int | float] = {}
    for event in events:
        # Pi emits cumulative usage on many message_update events. Counting only
        # final message_end events prevents the same model turn being duplicated.
        if event.get("type") != "message_end":
            continue
        message = event.get("message")
        usage = message.get("usage") if isinstance(message, dict) else None
        if not isinstance(usage, dict):
            continue
        token_fields = {
            "input_tokens": ("input", "inputTokens", "input_tokens"),
            "output_tokens": ("output", "outputTokens", "output_tokens"),
        }
        for target, aliases in token_fields.items():
            value = next((usage.get(key) for key in aliases if key in usage), None)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[target] = totals.get(target, 0) + value
        cache_value = sum(
            value
            for key in ("cacheRead", "cacheWrite", "cacheTokens", "cache_tokens")
            if isinstance((value := usage.get(key)), (int, float))
            and not isinstance(value, bool)
        )
        if cache_value or any(
            key in usage for key in ("cacheRead", "cacheWrite", "cacheTokens", "cache_tokens")
        ):
            totals["cache_tokens"] = totals.get("cache_tokens", 0) + cache_value
        cost = usage.get("cost")
        if isinstance(cost, dict):
            cost = cost.get("total")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            totals["cost"] = totals.get("cost", 0) + cost
    return totals


def _run_git(project_root: Path, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *arguments],
        cwd=str(project_root),
        shell=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise DelegationError("cli_failure", f"Git 基线检查失败：{result.stderr.strip()}")
    return result


def _parse_status_z(raw: str, project_root: Path, git_root: Path) -> dict[str, str]:
    entries = raw.split("\0")
    result: dict[str, str] = {}
    index = 0
    project_prefix = project_root.resolve().relative_to(git_root.resolve()).as_posix().rstrip("/")
    while index < len(entries) and entries[index]:
        entry = entries[index]
        code = entry[:2]
        path = entry[3:].replace("\\", "/")
        if code[0] in {"R", "C"}:
            index += 1
        if project_prefix and path.startswith(project_prefix + "/"):
            path = path[len(project_prefix) + 1 :]
        elif project_prefix and path != project_prefix:
            path = "../" + path
        result[path] = code
        index += 1
    return result


def _fingerprint(project_root: Path, path: str, code: str) -> str:
    if path.startswith("../"):
        return code
    target = project_root / Path(*PurePosixPath(path).parts)
    digest = hashlib.sha256()
    digest.update(code.encode("utf-8"))
    if target.is_file():
        with target.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    elif target.is_dir():
        digest.update(b"<DIR>")
    else:
        digest.update(b"<MISSING>")
    return digest.hexdigest()


def snapshot_git(project_root: Path = PROJECT_ROOT) -> GitSnapshot:
    git_root_result = _run_git(project_root, ["rev-parse", "--show-toplevel"])
    git_root = Path(git_root_result.stdout.strip())
    status = _run_git(
        project_root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"]
    )
    path_codes = _parse_status_z(status.stdout, project_root, git_root)
    fingerprints = {
        path: _fingerprint(project_root, path, code) for path, code in path_codes.items()
    }
    return GitSnapshot(bool(path_codes), set(path_codes), fingerprints)


def changed_by_delegate(before: GitSnapshot, after: GitSnapshot) -> list[str]:
    changed: list[str] = []
    for path in sorted(before.paths | after.paths):
        if before.fingerprints.get(path) != after.fingerprints.get(path):
            changed.append(path)
    return changed


def find_scope_violations(changed: list[str], allowed_paths: list[str]) -> list[str]:
    allowed = [item.replace("\\", "/").rstrip("/") for item in allowed_paths]
    violations: list[str] = []
    for path in changed:
        normal = path.replace("\\", "/")
        if not any(normal == item or normal.startswith(item + "/") for item in allowed):
            violations.append(normal)
    return sorted(violations)


def _relative(path: Path, project_root: Path = PROJECT_ROOT) -> str:
    return path.resolve().relative_to(project_root.resolve()).as_posix()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_log(record: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _classify_cli_failure(stdout: str, stderr: str) -> str:
    combined = (stdout + "\n" + stderr).lower()
    if any(marker in combined for marker in ("api key", "authenticate", "authentication", "login")):
        return "not_authenticated"
    if "model" in combined and any(marker in combined for marker in ("not found", "unknown", "no models")):
        return "model_not_found"
    return "cli_failure"


def check_runtime(config: dict[str, Any], project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    ensure_enabled(config)
    executable = locate_pi(config)
    version = invoke_pi([executable, "--version"], 30, project_root)
    if version.returncode != 0:
        raise DelegationError("cli_failure", "Pi --version 执行失败。", stderr=version.stderr)
    models = invoke_pi([executable, "--list-models", FIXED_PROVIDER], 60, project_root)
    combined = redact_sensitive_text(models.stdout + "\n" + models.stderr)
    if models.returncode != 0:
        raise DelegationError(
            "not_authenticated",
            "Pi 无法读取 OpenCode Go 模型。请运行 pi，执行 /login，并选择 OpenCode Go。",
            stdout=models.stdout,
            stderr=models.stderr,
            exit_code=models.returncode,
        )
    if not model_catalog_contains_fixed(combined):
        raise DelegationError(
            "model_not_found",
            f"OpenCode Go 模型目录中没有精确的 {FIXED_PROVIDER}/{FIXED_MODEL}；不会切换到免费版或其他模型。",
            stdout=models.stdout,
            stderr=models.stderr,
            exit_code=models.returncode,
        )
    return {
        "status": "success",
        "pi_command": executable,
        "pi_version": version.stdout.strip(),
        "provider": FIXED_PROVIDER,
        "model": FIXED_MODEL,
        "full_model": f"{FIXED_PROVIDER}/{FIXED_MODEL}",
        "authenticated": True,
    }


def init_router(
    config_path: Path = CONFIG_PATH, project_root: Path = PROJECT_ROOT
) -> dict[str, Any]:
    config = default_config()
    runtime = check_runtime(config, project_root)
    _write_json(config_path, config)
    try:
        saved_path = config_path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        saved_path = str(config_path.resolve())
    return {**runtime, "config_file": saved_path}


def run_task(
    task_path: Path,
    *,
    allow_dirty: bool,
    thinking: str | None,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    started_at = now_iso()
    started_clock = time.monotonic()
    task_id = task_path.stem
    status = "cli_failure"
    exit_code: int | None = None
    changed: list[str] = []
    violations: list[str] = []
    usage: dict[str, int | float] = {}
    raw_stdout = ""
    raw_stderr = ""
    dirty_before = False
    result_path = RESULTS_DIR / f"{task_id}.json"
    raw_path = RESULTS_DIR / f"{task_id}.pi.jsonl"
    try:
        task = load_task(task_path, project_root)
        task_id = task["task_id"]
        result_path = RESULTS_DIR / f"{task_id}.json"
        raw_path = RESULTS_DIR / f"{task_id}.pi.jsonl"
        config = load_config(project_root / ".agent-router" / "config.json")
        ensure_enabled(config)
        executable = locate_pi(config)
        before = snapshot_git(project_root)
        dirty_before = before.dirty
        if before.dirty and not allow_dirty:
            raise DelegationError(
                "dirty_worktree",
                "工作区存在未提交修改；默认拒绝委派。确认需要基于当前修改时使用 --allow-dirty。",
            )
        command = build_pi_command(executable, config, project_root, task_path, thinking=thinking)
        completed = invoke_pi(command, effective_timeout(task, config), project_root)
        exit_code = completed.returncode
        raw_stdout = completed.stdout
        raw_stderr = completed.stderr
        after = snapshot_git(project_root)
        changed = changed_by_delegate(before, after)
        violations = find_scope_violations(changed, task["allowed_paths"])
        if completed.returncode != 0:
            failure = _classify_cli_failure(completed.stdout, completed.stderr)
            raise DelegationError(
                failure,
                f"Pi 退出码为 {completed.returncode}；未切换模型或重试。",
                stdout=completed.stdout,
                stderr=completed.stderr,
                exit_code=completed.returncode,
            )
        events = parse_jsonl(completed.stdout)
        usage = extract_usage(events)
        status = "scope_violation" if violations else "success"
    except DelegationError as exc:
        status = exc.status
        raw_stdout = raw_stdout or exc.stdout
        raw_stderr = raw_stderr or exc.stderr
        exit_code = exit_code if exit_code is not None else exc.exit_code
        if status in {"timeout", "cli_failure", "not_authenticated", "model_not_found"}:
            try:
                if "before" in locals():
                    after = snapshot_git(project_root)
                    changed = changed_by_delegate(before, after)
                    if "task" in locals():
                        violations = find_scope_violations(changed, task["allowed_paths"])
                        if violations:
                            status = "scope_violation"
            except DelegationError:
                pass
        error_message = exc.message
    else:
        error_message = None
    finished_at = now_iso()
    duration = round(time.monotonic() - started_clock, 3)
    safe_stdout = redact_sensitive_text(raw_stdout)
    safe_stderr = redact_sensitive_text(raw_stderr)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(safe_stdout, encoding="utf-8")
    result: dict[str, Any] = {
        "task_id": task_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration,
        "engine": "pi",
        "provider": FIXED_PROVIDER,
        "model": FIXED_MODEL,
        "status": status,
        "exit_code": exit_code,
        "dirty_before": dirty_before,
        "files_changed": changed,
        "scope_violations": violations,
        "pi_output_file": _relative(raw_path, project_root),
    }
    if error_message:
        result["error"] = error_message
    if safe_stderr:
        result["stderr"] = safe_stderr
    result.update(usage)
    _write_json(result_path, result)
    log_record = dict(result)
    log_record["result_file"] = _relative(result_path, project_root)
    log_record.pop("stderr", None)
    _append_log(log_record)
    return result


def collect_stats(path: Path = LOG_PATH) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    if path.exists():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                warnings.append(f"忽略损坏的日志行 {number}")
                continue
            if isinstance(value, dict):
                records.append(value)
    successes = sum(record.get("status") == "success" for record in records)
    summary: dict[str, Any] = {
        "total_calls": len(records),
        "successes": successes,
        "failures": len(records) - successes,
        "timeouts": sum(record.get("status") == "timeout" for record in records),
        "scope_violations": sum(record.get("status") == "scope_violation" for record in records),
        "duration_seconds": sum(
            value for record in records if isinstance((value := record.get("duration_seconds")), (int, float))
        ),
        "recent": records[-5:],
    }
    for key in ("input_tokens", "output_tokens", "cache_tokens", "cost"):
        values = [record[key] for record in records if isinstance(record.get(key), (int, float))]
        if values:
            summary[key] = sum(values)
    if warnings:
        summary["warnings"] = warnings
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init", help="验证 Pi 登录并写入固定单模型配置")
    subparsers.add_parser("check", help="检查 Pi、认证和固定模型")
    run_parser = subparsers.add_parser("run", help="同步执行一个边界明确的任务")
    run_parser.add_argument("--task", required=True, type=Path)
    run_parser.add_argument("--allow-dirty", action="store_true")
    run_parser.add_argument("--thinking", choices=sorted(THINKING_LEVELS))
    subparsers.add_parser("stats", help="显示本地 JSONL 使用摘要")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "init":
            result = init_router()
        elif args.command == "check":
            result = check_runtime(load_config())
        elif args.command == "run":
            result = run_task(
                args.task,
                allow_dirty=args.allow_dirty,
                thinking=args.thinking,
            )
        else:
            result = collect_stats()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status", "success") == "success" else 1
    except DelegationError as exc:
        print(json.dumps({"status": exc.status, "error": exc.message}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
