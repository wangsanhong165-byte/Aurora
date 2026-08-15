"""Empty-reply handling: truncation detection + relaxation + fallback.

Regression coverage for the "model returns no visible text" failure chain:
  DeepSeek reasoning exhausts the output budget (finish_reason="length")
  -> adapter drops finish_reason -> empty reply validated as success
  -> frontend stuck on "正在组织语言…".

The fix threads finish_reason through the adapter/provider, treats an empty
reply as invalid, repairs once, and falls back to a spoken line when the
repair is also empty. The main chat path also gets an explicit relaxed
output budget so reasoning has room to finish the reply.
"""

import asyncio
from types import SimpleNamespace

from app.interfaces.llm import LLMResponse
from app.runtime.character_turn import CharacterTurn, TurnInput
from app.runtime.steps.decision_step import DecisionStep


def run(coro):
    return asyncio.run(coro)


def _fake_adapter_client(create):
    """Wrap a create(**kwargs) callable as the OpenAI SDK client shape."""
    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )


def _fake_completion(content="", finish_reason="stop"):
    message = SimpleNamespace(
        content=content,
        reasoning_content=None,
        tool_calls=[],
    )
    usage = SimpleNamespace(
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        prompt_tokens_details=None,
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason=finish_reason)],
        usage=usage,
        model="deepseek-v4-flash",
    )


def _make_adapter(create):
    from app.models.http_adapters import OpenAILLMAdapter

    adapter = object.__new__(OpenAILLMAdapter)
    adapter._model = "deepseek-v4-flash"
    adapter._max_tool_rounds = 5
    adapter._temperature = 0.3
    adapter._client = _fake_adapter_client(create)
    return adapter


# ── OpenAILLMAdapter: finish_reason + forward the relaxed budget ──────────


def test_adapter_captures_finish_reason_on_truncated_empty():
    """A reasoning-truncated response keeps its finish_reason and empty content."""
    create = lambda **kw: _fake_completion(content=None, finish_reason="length")
    result = _make_adapter(create).generate([{"role": "user", "content": "hi"}])

    assert result["finish_reason"] == "length"
    assert result["content"] == ""


def test_adapter_keeps_finish_reason_stop_for_normal_reply():
    create = lambda **kw: _fake_completion(content="hello", finish_reason="stop")
    result = _make_adapter(create).generate([{"role": "user", "content": "hi"}])

    assert result["finish_reason"] == "stop"
    assert result["content"] == "hello"


def test_adapter_forwards_max_tokens_and_reasoning_effort():
    captured = {}

    def create(**kw):
        captured.update(kw)
        return _fake_completion(content="ok")

    result = _make_adapter(create).generate(
        [{"role": "user", "content": "hi"}],
        max_tokens=16384,
        reasoning_effort="low",
    )
    assert result["finish_reason"] == "stop"
    assert captured["max_tokens"] == 16384
    assert captured["reasoning_effort"] == "low"


def test_adapter_omits_reasoning_effort_when_unset():
    captured = {}

    def create(**kw):
        captured.update(kw)
        return _fake_completion(content="ok")

    _make_adapter(create).generate([{"role": "user", "content": "hi"}])
    assert "reasoning_effort" not in captured
    assert "max_tokens" not in captured


def test_adapter_resolves_opencode_engine(monkeypatch):
    """LLM_ENGINE=opencode points the adapter at the OpenCode local server."""
    from app.models.http_adapters import OpenAILLMAdapter

    monkeypatch.setenv("LLM_ENGINE", "opencode")
    monkeypatch.setenv("OPENCODE_BASE_URL", "http://127.0.0.1:4096/v1")
    monkeypatch.setenv("OPENCODE_MODEL", "opencode")
    monkeypatch.setenv("OPENCODE_API_KEY", "local")

    adapter = OpenAILLMAdapter()

    assert adapter._base_url == "http://127.0.0.1:4096/v1"
    assert adapter._model == "opencode"
    assert adapter._api_key == "local"


def test_adapter_defaults_opencode_url(monkeypatch):
    """Unset OPENCODE_* falls back to the documented OpenCode serve defaults."""
    from app.models.http_adapters import OpenAILLMAdapter

    monkeypatch.setenv("LLM_ENGINE", "opencode")
    monkeypatch.delenv("OPENCODE_BASE_URL", raising=False)
    monkeypatch.delenv("OPENCODE_MODEL", raising=False)
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)

    adapter = OpenAILLMAdapter()

    assert adapter._base_url == "http://127.0.0.1:4096/v1"
    assert adapter._model == "opencode"
    assert adapter._api_key == "local"


def test_adapter_keeps_deepseek_default_when_engine_unset(monkeypatch):
    """Without LLM_ENGINE=opencode the adapter keeps the DeepSeek path."""
    from app.models.http_adapters import OpenAILLMAdapter

    monkeypatch.delenv("LLM_ENGINE", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("LLM_MODEL", "deepseek-v4-flash")

    adapter = OpenAILLMAdapter()

    assert adapter._base_url == "https://api.deepseek.com"
    assert adapter._model == "deepseek-v4-flash"


# ── OpenAILLMProvider: thread finish_reason, relax max_tokens ─────────────


def test_provider_threads_finish_reason_into_llm_response():
    from app.providers.llm.openai_adapter import OpenAILLMProvider

    provider = object.__new__(OpenAILLMProvider)
    response = provider._normalize({
        "content": "",
        "reasoning": "…thinking…",
        "finish_reason": "length",
        "tool_calls": [],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "model": "deepseek-v4-flash",
    }, [{"role": "user", "content": "hi"}])

    assert response.reply == ""
    assert response.finish_reason == "length"


def test_provider_defaults_to_relaxed_max_tokens(monkeypatch):
    from app.providers.llm.openai_adapter import OpenAILLMProvider

    monkeypatch.delenv("LLM_MAX_TOKENS", raising=False)
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)

    class Recorder:
        model = "deepseek-v4-flash"

        def __init__(self):
            self.kwargs = None

        def generate(self, messages, **kwargs):
            self.kwargs = kwargs
            return {"content": '{"final_reply": "hi", "segments": []}', "reasoning": "",
                    "finish_reason": "stop", "tool_calls": [], "usage": {}, "model": "deepseek-v4-flash"}

    provider = OpenAILLMProvider.__new__(OpenAILLMProvider)
    provider._adapter = Recorder()
    response = run(provider.generate([{"role": "user", "content": "x"}]))

    assert provider._adapter.kwargs["max_tokens"] == 8192
    assert provider._adapter.kwargs.get("reasoning_effort") is None
    assert response.reply == "hi"


def test_provider_honors_env_max_tokens_and_reasoning_effort(monkeypatch):
    from app.providers.llm.openai_adapter import OpenAILLMProvider

    monkeypatch.setenv("LLM_MAX_TOKENS", "4096")
    monkeypatch.setenv("LLM_REASONING_EFFORT", "low")

    class Recorder:
        model = "deepseek-v4-flash"

        def __init__(self):
            self.kwargs = None

        def generate(self, messages, **kwargs):
            self.kwargs = kwargs
            return {"content": "ok", "reasoning": "", "finish_reason": "stop",
                    "tool_calls": [], "usage": {}, "model": "deepseek-v4-flash"}

    provider = OpenAILLMProvider.__new__(OpenAILLMProvider)
    provider._adapter = Recorder()
    run(provider.generate([{"role": "user", "content": "x"}]))

    assert provider._adapter.kwargs["max_tokens"] == 4096
    assert provider._adapter.kwargs["reasoning_effort"] == "low"


# ── ResponseValidator: empty reply is invalid ──────────────────────────────


def test_validator_marks_empty_reply_invalid():
    from app.runtime.response_validator import ResponseValidator

    result = ResponseValidator().validate("", [])
    assert result.valid is False
    assert result.reply == ""


def test_validator_marks_empty_text_segments_invalid():
    from app.runtime.response_validator import ResponseValidator

    result = ResponseValidator().validate("", [
        {"text": "", "emotion": "neutral", "behavior": "speak"},
    ])
    assert result.valid is False


def test_validator_marks_whitespace_only_reply_invalid():
    """Whitespace-only content must not be recovered into a phantom segment."""
    from app.runtime.response_validator import ResponseValidator

    result = ResponseValidator().validate("   ", [])
    assert result.valid is False
    assert result.reply == ""
    assert result.segments == []

    newline_result = ResponseValidator().validate("\t\n  ", [])
    assert newline_result.valid is False
    assert newline_result.segments == []


def test_validator_keeps_non_empty_reply_valid():
    from app.runtime.response_validator import ResponseValidator

    assert ResponseValidator().validate("hello", []).valid is True
    assert ResponseValidator().validate(
        "", [{"text": "hello", "emotion": "neutral", "behavior": "speak"}]
    ).valid is True


def test_llm_response_finish_reason_defaults_to_empty():
    assert LLMResponse().finish_reason == ""


# ── DecisionStep: repair truncated-empty, fall back when repair fails ─────


def test_decision_step_repairs_truncated_empty_reply_once():
    class TruncatedThenRepairedLLM:
        def __init__(self):
            self.calls = 0

        async def generate(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(reply="", finish_reason="length")
            return LLMResponse(
                reply="fixed",
                segments=[{"text": "fixed", "emotion": "neutral", "behavior": "speak"}],
            )

    llm = TruncatedThenRepairedLLM()
    ctx = CharacterTurn(input=TurnInput(text="hello"))
    run(DecisionStep(llm).run(ctx))

    assert llm.calls == 2
    assert ctx.reply_text == "fixed"


def test_decision_step_falls_back_when_repair_is_also_empty():
    class TwiceEmptyLLM:
        def __init__(self):
            self.calls = 0

        async def generate(self, messages, **kwargs):
            self.calls += 1
            return LLMResponse(reply="", finish_reason="stop")

    llm = TwiceEmptyLLM()
    ctx = CharacterTurn(input=TurnInput(text="hello"))
    run(DecisionStep(llm).run(ctx))

    assert llm.calls == 2
    assert ctx.reply_text == "我刚才走神了，能再跟我说一遍吗？"
    assert ctx.segments[0]["contextTags"] == ["empty_reply_fallback"]
    assert ctx.output.performance.speaking is True


def test_decision_step_repairs_whitespace_only_reply_and_falls_back():
    """Whitespace-only content must trigger repair, then fall back if needed."""

    class WhitespaceThenEmptyLLM:
        def __init__(self):
            self.calls = 0

        async def generate(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(reply="   \n  ", finish_reason="stop")
            return LLMResponse(reply="", finish_reason="length")

    llm = WhitespaceThenEmptyLLM()
    ctx = CharacterTurn(input=TurnInput(text="hello"))
    run(DecisionStep(llm).run(ctx))

    assert llm.calls == 2
    assert ctx.reply_text == "我刚才走神了，能再跟我说一遍吗？"
    assert ctx.segments[0]["contextTags"] == ["empty_reply_fallback"]


def test_decision_step_keeps_whitespace_trimmed_real_reply():
    """A reply that trims to real text is used as-is (no repair)."""

    class TrimmedLLM:
        def __init__(self):
            self.calls = 0

        async def generate(self, messages, **kwargs):
            self.calls += 1
            return LLMResponse(
                reply="  你好呀  ",
                segments=[{"text": "  你好呀  ", "emotion": "neutral", "behavior": "speak"}],
            )

    llm = TrimmedLLM()
    ctx = CharacterTurn(input=TurnInput(text="hello"))
    run(DecisionStep(llm).run(ctx))

    assert llm.calls == 1
    assert ctx.reply_text == "你好呀"


def test_decision_step_fallback_text_is_configurable(monkeypatch):
    monkeypatch.setenv("LLM_EMPTY_REPLY_FALLBACK", "再试一次？")

    class TwiceEmptyLLM:
        async def generate(self, messages, **kwargs):
            return LLMResponse(reply="", finish_reason="length")

    ctx = CharacterTurn(input=TurnInput(text="hello"))
    run(DecisionStep(TwiceEmptyLLM()).run(ctx))

    assert ctx.reply_text == "再试一次？"


def test_decision_step_does_not_repair_a_normal_reply():
    class NormalLLM:
        def __init__(self):
            self.calls = 0

        async def generate(self, messages, **kwargs):
            self.calls += 1
            return LLMResponse(
                reply="hello",
                segments=[{"text": "hello", "emotion": "neutral", "behavior": "speak"}],
            )

    llm = NormalLLM()
    ctx = CharacterTurn(input=TurnInput(text="hello"))
    run(DecisionStep(llm).run(ctx))

    assert llm.calls == 1
    assert ctx.reply_text == "hello"


def test_default_planner_requires_nonempty_reply():
    """The output protocol must forbid empty/whitespace-only replies."""
    from app.runtime.default_planner import DefaultPlanner
    from app.domain.character import Character

    ctx = CharacterTurn(input=TurnInput(text="hi"))
    ctx.character = Character({
        "id": "monika", "name": {"en": "Monika"}, "character_setting": "Be natural.",
    })
    plan = DefaultPlanner().plan(ctx)
    prompt = " ".join(
        m["content"] for m in plan.messages if m["role"] == "system"
    )
    assert "Never return empty, blank, or whitespace-only content" in prompt


def test_decision_step_fallback_not_written_to_conversation_history():
    """The recovery line must not pollute the LLM conversation context."""

    class TwiceEmptyLLM:
        async def generate(self, messages, **kwargs):
            return LLMResponse(reply="", finish_reason="stop")

    class RecordingConversation:
        def __init__(self):
            self.turns = []

        def add_turn(self, role, content, **metadata):
            self.turns.append((role, content))

        def get_history(self, limit=10):
            return [
                {"role": role, "content": content}
                for role, content in self.turns[-limit:]
            ]

    conv = RecordingConversation()
    ctx = CharacterTurn(input=TurnInput(text="hello"))
    ctx.conversation = conv
    run(DecisionStep(TwiceEmptyLLM()).run(ctx))

    assert ctx.reply_text == "我刚才走神了，能再跟我说一遍吗？"
    assert conv.turns == [("user", "hello")]
    assert any(w.startswith("assistant_reply_fallback") for w in ctx.warnings)


def test_decision_step_keeps_plain_text_reply_when_repair_fails():
    """A usable plain-text reply survives a failed repair — no fallback line.

    When tools are present the adapter stops forcing JSON output, so DeepSeek
    answers in prose. The validator rejects multi-sentence prose as
    "unstructured", but discarding it for a failed repair would lose the reply.
    """

    class PlainTextThenEmptyLLM:
        def __init__(self):
            self.calls = 0

        async def generate(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(reply="嗨，我在呢。刚不是还在聊鬼的事嘛，今天想写点啥？")
            return LLMResponse(reply="", finish_reason="stop")

    llm = PlainTextThenEmptyLLM()
    ctx = CharacterTurn(input=TurnInput(text="hi"))
    run(DecisionStep(llm).run(ctx))

    assert llm.calls == 2
    assert ctx.reply_text == "嗨，我在呢。刚不是还在聊鬼的事嘛，今天想写点啥？"
    assert "assistant_reply_recovered" in ctx.warnings
    assert not any(w.startswith("assistant_reply_fallback") for w in ctx.warnings)
