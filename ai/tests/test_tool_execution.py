import asyncio
import json

from app.runtime.tool_execution import ToolExecutionSupervisor


def run(coro):
    return asyncio.run(coro)


def test_read_only_tool_retries_once_and_audits_without_argument_values():
    class Flaky:
        def __init__(self):
            self.calls = 0

        async def execute(self, name, args):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary")
            return "ok"

    provider = Flaky()
    result = run(ToolExecutionSupervisor(1, 2).execute(
        provider, "lookup", {"secret": "do-not-log"}, "read_only"
    ))
    assert result.text == "ok"
    assert result.audit["attempts"] == 2
    assert result.audit["argument_keys"] == ["secret"]
    assert "do-not-log" not in str(result.audit)


def test_side_effecting_tool_does_not_retry():
    class Broken:
        def __init__(self):
            self.calls = 0

        async def execute(self, name, args):
            self.calls += 1
            raise RuntimeError("failed")

    provider = Broken()
    result = run(ToolExecutionSupervisor(1, 3).execute(
        provider, "write_note", {}, "confirm"
    ))
    assert provider.calls == 1
    assert result.audit["status"] == "error"


def test_tool_timeout_returns_structured_error():
    class Slow:
        async def execute(self, name, args):
            await asyncio.sleep(1)
            return "late"

    result = run(ToolExecutionSupervisor(0.05, 1).execute(
        Slow(), "slow", {}, "read_only"
    ))
    assert json.loads(result.text)["error"] == "tool_timeout"
    assert result.audit["status"] == "timeout"
