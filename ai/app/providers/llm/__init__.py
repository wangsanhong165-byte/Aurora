"""LLM providers — registered on import."""
import os

from app.interfaces.llm import LLMInterface, MockLLM, ReplayLLM
from app.providers.registry import provider_registry

# Register mock for testing / development
provider_registry.register(LLMInterface, "mock", MockLLM)
provider_registry.register(LLMInterface, "replay", ReplayLLM)

# Register real provider if env is configured; "default" alias always resolves
api_key = (
    os.environ.get("DEEPSEEK_API_KEY")
    or os.environ.get("OPENAI_API_KEY")
    or os.environ.get("OPENCODE_API_KEY")
)
if api_key:
    from app.providers.llm.openai_adapter import OpenAILLMProvider

    provider_registry.register(LLMInterface, "openai", OpenAILLMProvider)
    provider_registry.register(LLMInterface, "opencode", OpenAILLMProvider)
    provider_registry.register(LLMInterface, "default", OpenAILLMProvider)
else:
    provider_registry.register(LLMInterface, "default", MockLLM)
