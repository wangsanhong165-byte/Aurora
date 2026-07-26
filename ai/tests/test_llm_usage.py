from app.interfaces.llm import LLMResponse, LLMUsage


def test_llm_usage_accumulates_tool_rounds():
    response = LLMResponse()
    response.add_usage(LLMUsage(prompt_tokens=100, completion_tokens=20, cached_tokens=50))
    response.add_usage(LLMUsage(prompt_tokens=130, completion_tokens=30, cached_tokens=80))

    assert response.usage.prompt_tokens == 230
    assert response.usage.completion_tokens == 50
    assert response.usage.total_tokens == 280
    assert response.usage.cached_tokens == 130
