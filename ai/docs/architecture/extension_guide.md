# Extension Guide

> **Date**: 2026-06-29
> **Constitution ref**: §7
> **Audience**: Developers adding new capabilities to the Companion Runtime

---

## How to Add a New LLM Provider

### Step 1: Implement the Interface

Create `app/providers/llm/my_provider.py`:

```python
from app.interfaces.llm import LLMInterface, LLMResponse

class MyLLMProvider(LLMInterface):
    def __init__(self, api_key=None, base_url=None, model=None):
        # Initialize your client
        pass

    async def generate(self, messages, **kwargs) -> LLMResponse:
        # 1. Call your LLM API
        # 2. Normalize the response into LLMResponse
        # 3. Return LLMResponse(reply=..., segments=..., tool_calls=..., messages=..., error=...)
        pass

    async def generate_stream(self, messages, **kwargs) -> AsyncIterator[str]:
        # Yield token strings
        pass
```

### Step 2: Register

In `app/providers/llm/__init__.py`:

```python
from app.providers.llm.my_provider import MyLLMProvider
provider_registry.register(LLMInterface, "my_provider", MyLLMProvider)
```

### Step 3: Configure

Set environment variables or update config to point to your provider.

**No Runtime modification required.** Provider replacement requires only registration.

---

## How to Add a New TTS/ASR/Memory/Live2D/Tool Provider

Same pattern as LLM provider — implement the Interface, register in the provider's `__init__.py`, configure via env.

### Pattern:

```python
# app/providers/<name>/__init__.py
from app.interfaces.<iface> import <Interface>
from app.providers.registry import provider_registry

# Register mock for testing
provider_registry.register(<Interface>, "mock", Mock<Interface>)

# Register real provider if configured
if os.environ.get("<ENV_VAR>"):
    from app.providers.<name>.my_provider import MyProvider
    provider_registry.register(<Interface>, "my_provider", MyProvider)
    provider_registry.register(<Interface>, "default", MyProvider)
else:
    provider_registry.register(<Interface>, "default", Mock<Interface>)
```

---

## How to Add a New Pipeline Step

### Step 1: Create the Step

Create `app/runtime/steps/my_step.py`:

```python
from app.runtime.pipeline import Step
from app.runtime.context import Context

class MyStep(Step):
    """Do something with the pipeline context."""

    def __init__(self, some_dependency):
        self._dep = some_dependency

    async def run(self, ctx: Context) -> None:
        # Read from ctx
        value = ctx.state.get("some_key")
        # Write to ctx
        ctx.state["my_result"] = await self._dep.do_something(value)
        # On error:
        # ctx.error = "description"
```

### Step 2: Register in the Pipeline

In `CompanionRuntime._build_pipeline_steps()` (`app/runtime/runtime.py`):

```python
from app.runtime.steps import MyStep

def _build_pipeline_steps(self, providers, character):
    return [
        ASRStep(providers["asr"]),
        CharacterStep(character),
        MemoryRetrieveStep(providers["memory"]),
        MyStep(providers.get("my_dep")),          # <-- add here
        DecisionStep(providers["llm"], tool_provider=providers["tool"]),
        EmotionStep(),
        MemorySaveStep(providers["memory"]),
        TTSStep(providers["tts"]),
        Live2DStep(providers["live2d"]),
    ]
```

### Step 3 (optional): Export from `__init__.py`

```python
# app/runtime/steps/__init__.py
from app.runtime.steps.my_step import MyStep
```

**Note**: Adding a step does NOT require modifying existing Steps. Each Step is independent.

---

## How to Add a New Event Type

### Step 1: Define the constant

In `app/runtime/event.py`:

```python
class EventType:
    # ...existing constants...
    MY_NEW_EVENT = "my_new_event"
```

### Step 2 (optional): Handle in Runtime dispatch

In `CompanionRuntime.dispatch()` if the new event type needs special routing:

```python
if event.type == EventType.MY_NEW_EVENT:
    ctx.user_text = event.payload.get("my_field", "")
```

### Step 3: Add a Step

Create a Step that checks for and reacts to the new event type:

```python
class MyStep(Step):
    async def run(self, ctx: Context) -> None:
        if ctx.event.type == EventType.MY_NEW_EVENT:
            # Handle it
            ctx.state["result"] = process(ctx.event.payload)
```

---

## How to Add a New Background Service

### Step 1: Create the service

In `app/services/my_service.py`:

```python
import threading

class MyService:
    def __init__(self, interval: float = 60.0):
        self.interval = interval
        self._timer: threading.Timer | None = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._schedule()

    def stop(self) -> None:
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _schedule(self) -> None:
        if not self._running:
            return
        self._timer = threading.Timer(self.interval, self._tick)
        self._timer.daemon = True
        self._timer.start()

    def _tick(self) -> None:
        try:
            self._check()
        finally:
            self._schedule()

    def _check(self) -> None:
        # Push events to initiative_queue or update state_store
        pass
```

### Step 2: Wire into Runtime

In `CompanionRuntime` (`app/runtime/runtime.py`):

```python
def _setup_pipeline(self):
    # ... existing setup ...
    self._init_my_service()

def _init_my_service(self):
    from app.services.my_service import MyService
    self.my_service = MyService(interval=30.0)
    self.my_service.start()

def shutdown(self):
    # ... existing shutdown ...
    if self.my_service is not None:
        self.my_service.stop()
```

---

## How to Add a New Built-in Tool

### Step 1: Implement the tool function

In `app/legacy/tools/builtins/my_tool.py`:

```python
def my_tool(arg1: str, arg2: int = 0) -> str:
    """Do something useful.
    
    Args:
        arg1: Description of arg1
        arg2: Description of arg2 (default: 0)
    """
    result = do_work(arg1, arg2)
    return json.dumps({"result": result})
```

### Step 2: Register

In the `_register_all` function:

```python
def _register_all(registry):
    # ...existing registrations...
    registry.register("my_tool", my_tool, {
        "type": "function",
        "function": {
            "name": "my_tool",
            "description": "Do something useful",
            "parameters": {
                "type": "object",
                "properties": {
                    "arg1": {"type": "string", "description": "..."},
                    "arg2": {"type": "integer", "description": "..."},
                },
                "required": ["arg1"],
            },
        },
    })
```

---

## Summary: Extension Matrix

| Extension | Files to create | Files to modify | Runtime change? |
|-----------|----------------|----------------|-----------------|
| New LLM provider | `app/providers/llm/my_p.py` | `app/providers/llm/__init__.py` | No |
| New TTS/ASR/Memory/Live2D/Tool provider | `app/providers/<name>/my_p.py` | `app/providers/<name>/__init__.py` | No |
| New Pipeline Step | `app/runtime/steps/my_step.py` | `app/runtime/runtime.py`, `app/runtime/steps/__init__.py` | Yes (pipeline step list) |
| New Event Type | None | `app/runtime/event.py` | Optional (if special routing needed) |
| New Background Service | `app/services/my_service.py` | `app/runtime/runtime.py` | Yes (lifecycle hook) |
| New Built-in Tool | `app/legacy/tools/builtins/my_tool.py` | registry initialization file | No |
