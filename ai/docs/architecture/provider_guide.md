# Provider Guide

> **Date**: 2026-06-29
> **Audience**: Developers working with or debugging the Provider registration system

---

## Architecture

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Runtime     │ ──▶ │ ProviderFactory  │ ──▶ │ ProviderRegistry │
│  (consumer)  │     │ .create(Iface)   │     │ (singleton)      │
└──────────────┘     └──────────────────┘     └──────────────────┘
                                                    │
                                          register(Interface, name, Class)
                                                    │
                          ┌─────────────────────────┼─────────────────┐
                          │                         │                  │
                 ┌────────▼──────┐        ┌─────────▼──────┐   ┌─────▼────────┐
                 │ providers/llm │        │ providers/tts  │   │ providers/asr │
                 │ __init__.py   │        │ __init__.py    │   │ __init__.py   │
                 └───────────────┘        └────────────────┘   └──────────────┘
```

---

## Provider Discovery

`ProviderFactory.discover()` is called once (lazy, on first `create()`) and imports all known provider packages. Each package's `__init__.py` registers implementations as a side effect.

```python
# app/providers/factory.py
_PROVIDER_PACKAGES = [
    "app.providers.llm",
    "app.providers.tts",
    "app.providers.asr",
    "app.providers.memory",
    "app.providers.tool",
    "app.providers.live2d",
]
for pkg in _PROVIDER_PACKAGES:
    __import__(pkg)  # triggers __init__.py → register(Interface, name, Class)
```

---

## Registration Pattern

Each provider package uses this consistent pattern:

```python
# app/providers/<name>/__init__.py

# 1. Import interface + mock
from app.interfaces.<iface> import <Interface>, Mock<Interface>
from app.providers.registry import provider_registry

# 2. Register mock for testing
provider_registry.register(<Interface>, "mock", Mock<Interface>)

# 3. Register real provider if configured
if <condition>:  # env var, config file exists, etc.
    from app.providers.<name>.real_provider import RealProvider
    provider_registry.register(<Interface>, "<name>", RealProvider)
    provider_registry.register(<Interface>, "default", RealProvider)
else:
    provider_registry.register(<Interface>, "default", Mock<Interface>)
```

The `"default"` name is the fallback — when `ProviderFactory.create(Interface)` is called without a name, it resolves `"default"`.

---

## Resolution Chain

```python
provider_registry.resolve(LLMInterface, "deepseek")
# → key = (LLMInterface, "deepseek")
# → if not found, key = (LLMInterface, "default")
# → if not found, return None

ProviderFactory.create(LLMInterface)
# → resolve(LLMInterface, "default")
# → instantiate the class with no kwargs
```

---

## Provider Lifecycle

| Interface | start() | shutdown() | Lifecycle owner |
|-----------|---------|------------|-----------------|
| LLMInterface | — | — | Runtime (none needed) |
| TTSInterface | — | — | Runtime (none needed) |
| ASRInterface | — | — | Runtime (none needed) |
| MemoryInterface | ✅ `start(registry, llm)` | ✅ `shutdown()` | Runtime |
| ToolInterface | — | ✅ `shutdown()` (MCP) | Runtime (delegated) |
| Live2DInterface | ✅ `start()` (audio player) | ✅ `shutdown()` | Runtime (delegated) |

Only `MemoryInterface` and `BridgeLive2DProvider` have background threads that need lifecycle management. The rest are stateless or connection-based.

---

## Provider Map

| Provider key | Interface | Default class | Config condition | Fallback |
|-------------|-----------|--------------|-----------------|----------|
| `llm` | LLMInterface | OpenAILLMProvider | `DEEPSEEK_API_KEY` or `OPENAI_API_KEY` set | MockLLM |
| `tts` | TTSInterface | HTTPTTSProvider | `TTS_URL` or `TTS_PORT` set | MockTTS |
| `asr` | ASRInterface | HTTPASRProvider | `ASR_URL` or `ASR_PORT` set | MockASR |
| `memory` | MemoryInterface | SQLiteMemory | Always registered (no env guard) | N/A (always real) |
| `tool` | ToolInterface | LegacyToolProvider | `config/mcp_servers.json` exists | MockTool |
| `live2d` | Live2DInterface | BridgeLive2DProvider | `config/live2d_models.json` exists | MockLive2D |

---

## Common Provider Issues

### Issue: Provider resolves to Mock unexpectedly

Check the config condition. For example, `LegacyToolProvider` requires `config/mcp_servers.json` to exist. If the file doesn't exist, `MockTool` is registered as default.

### Issue: Provider import fails during discovery

`ProviderFactory.discover()` catches and silently skips import errors. Check that all dependencies are installed and env vars are set.

### Issue: Sync adapter blocks the event loop

All providers wrap synchronous adapters via `asyncio.to_thread()`. If a provider doesn't use `to_thread`, it will block. Pattern:

```python
async def generate(self, messages, **kwargs) -> LLMResponse:
    result = await asyncio.to_thread(self._adapter.generate, messages, ...)
    return self._normalize(result, messages)
```
