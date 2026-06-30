"""CompanionRuntime — the single entry point for all events.

Usage:
    from app.runtime.runtime import runtime
    from app.runtime.event import Event

    ctx = await runtime.dispatch(Event("text_received", {"text": "hello"}))
"""

from __future__ import annotations

import os

from app.core.initiative_queue import initiative_queue
from app.core.intent import compute_candidates, decide_action
from app.core.state import mood_tracker, state_store as core_state_store
from app.runtime.event import Event, EventType
from app.runtime.context import Context
from app.runtime.pipeline import Pipeline
from app.runtime.prompts import build_initiative_prompt
from app.runtime.state_store import state_store


class CompanionRuntime:
    """Central runtime. Holds a Pipeline and dispatches Events through it.

    Subclasses can override PROVIDER_BINDINGS to change which interfaces
    are resolved, or override _build_pipeline_steps() to change the
    pipeline step composition — all without modifying Runtime internals.
    """

    def __init__(self):
        self.pipeline = Pipeline()
        self.providers: dict = {}
        self.conversation = None  # set during _setup_pipeline
        self.initiative_checker = None  # InitiativeChecker, set during _setup_pipeline
        self.screen_watcher = None      # ScreenWatcher, set during _setup_pipeline
        self._character_registry = None
        self._initiative_cooldown: float = 120.0
        self._last_initiative_time: float = 0.0
        self._setup_pipeline()

    def _setup_pipeline(self):
        """Register default Steps and wire providers.

        Subclasses can override _get_provider_bindings() or
        _build_pipeline_steps() to customize without touching Runtime.
        """
        from app.providers.factory import ProviderFactory

        # Resolve providers from bindings
        for iface, key in self._get_provider_bindings():
            try:
                self.providers[key] = ProviderFactory.create(iface)
            except ValueError:
                self.providers[key] = self._fallback_provider(key.capitalize())

        # Build pipeline steps from factory
        from app.domain.character import Character
        from app.domain.conversation import Conversation

        character = self._load_character()
        self.conversation = Conversation()

        for step in self._build_pipeline_steps(self.providers, character):
            if step is not None:
                self.pipeline.add(step)

        # Save to state store
        state_store.set("runtime_initialized", True)

        # ── Background services ─────────────────────────────────────
        self._init_memory_ticker()
        self._init_initiative_system()
        self._init_screen_watcher()

    def _get_provider_bindings(self) -> list[tuple[type, str]]:
        """Return (InterfaceClass, provider_key) pairs for provider resolution.

        Override in subclass to add/remove capabilities. Each entry is
        resolved via ProviderFactory.create(InterfaceClass) and stored
        in self.providers under the given key name.
        """
        from app.interfaces.llm import LLMInterface
        from app.interfaces.tts import TTSInterface
        from app.interfaces.asr import ASRInterface
        from app.interfaces.memory import MemoryInterface
        from app.interfaces.live2d import Live2DInterface
        from app.interfaces.tool import ToolInterface

        return [
            (LLMInterface, "llm"),
            (MemoryInterface, "memory"),
            (ToolInterface, "tool"),
            (TTSInterface, "tts"),
            (ASRInterface, "asr"),
            (Live2DInterface, "live2d"),
        ]

    def _build_pipeline_steps(self, providers: dict, character: Any) -> list:
        """Return the ordered list of Pipeline steps.

        Override in subclass to recompose the pipeline (add/remove/reorder
        steps). Each element should be a Step instance or None (skipped).
        """
        from app.runtime.steps import (
            ASRStep, MemoryRetrieveStep, MemorySaveStep, CharacterStep,
            EmotionStep, DecisionStep, TTSStep, Live2DStep,
        )

        return [
            ASRStep(providers["asr"]),
            CharacterStep(character),
            MemoryRetrieveStep(providers["memory"]),
            DecisionStep(providers["llm"], tool_provider=providers["tool"]),
            EmotionStep(),
            MemorySaveStep(providers["memory"]),
            TTSStep(providers["tts"]),
            Live2DStep(providers["live2d"]),
        ]

    def switch_character(self, character_id: str) -> dict:
        """Switch the active character at runtime.

        Returns dict with keys: character_id, name, error (if failed).
        Bridge uses this instead of directly accessing CharacterRegistry.
        """
        from app.character.registry import CharacterRegistry
        from app.domain.character import Character

        try:
            reg = CharacterRegistry()
            reg.activate(character_id)
            self._character_registry = reg
            card = reg.active
            name = card.get("name", {}).get("zh", card.get("id", "AI"))
            # Notify memory compiler of character switch
            from app.memory import on_character_switch
            on_character_switch(None, character_id)
            return {"character_id": character_id, "name": name}
        except Exception as exc:
            return {"character_id": character_id, "error": str(exc)}

    def get_character_info(self) -> dict:
        """Return current character info for the bridge.

        Returns dict with keys: character_id, name, card.
        """
        if self._character_registry is None:
            return {"character_id": "default", "name": "Assistant", "card": {}}
        cid = self._character_registry.active_id or ""
        card = self._character_registry.active or {}
        name = card.get("name", {}).get("zh", card.get("id", "AI"))
        return {"character_id": cid, "name": name, "card": card}

    def _load_character(self) -> Character:
        """Load the active character from config."""
        from app.character.registry import CharacterRegistry
        from app.domain.character import Character

        try:
            self._character_registry = CharacterRegistry()
            card = self._character_registry.active
            return Character(card)
        except Exception:
            self._character_registry = None
            # Fallback: minimal character
            return Character({
                "id": "default",
                "name": {"zh": "助手", "en": "Assistant"},
                "system_prompt": "You are a helpful assistant.",
            })

    def _init_memory_ticker(self):
        """Initialize the memory provider's background tasks.

        Delegates entirely to the Memory provider's start() method, which
        manages MemoryStore startup, MemoryTicker lifecycle, and compiler
        setup internally.
        """
        memory_provider = self.providers.get("memory")
        if memory_provider is not None and hasattr(memory_provider, "start"):
            memory_provider.start(
                character_registry=self._character_registry,
                llm_provider=self.providers.get("llm"),
            )

    def _init_initiative_system(self):
        """Initialize InitiativeChecker — background proactive speech monitor.

        Drains the initiative queue periodically and dispatches
        INITIATIVE_TRIGGERED events through the Runtime pipeline when
        the agent should proactively speak.
        """
        from app.services.initiative_checker import InitiativeChecker

        idle_sec = float(os.environ.get("INITIATIVE_IDLE_SEC", "300"))
        check_sec = float(os.environ.get("INITIATIVE_CHECK_SEC", "15"))

        self.initiative_checker = InitiativeChecker(
            interval=check_sec, idle_threshold=idle_sec,
        )
        self.initiative_checker.on_initiative = self._on_initiative
        self.initiative_checker.start()
        # Also start the initiative buffer expiry thread
        from app.core.initiative_buffer import initiative_buffer
        initiative_buffer.start_expiry()

    def _on_initiative(self, events: list) -> None:
        """Called by InitiativeChecker when agent should proactively speak.

        Uses the intent engine to decide what to say, builds an initiative
        prompt, and dispatches it as an INITIATIVE_TRIGGERED event through
        the Runtime pipeline.
        """
        import time

        if self.providers.get("llm") is None:
            return

        # Cooldown check: prevent spamming from rapid screen_change events
        elapsed_since_last = time.time() - self._last_initiative_time
        if elapsed_since_last < self._initiative_cooldown and self._last_initiative_time > 0:
            return

        # Step 1: compute initiative candidates from live state
        idle = time.time() - self.initiative_checker._last_interaction
        ctx = core_state_store.snapshot()
        candidates = compute_candidates(
            idle, mood_tracker.mood,
            activity=ctx.get("activity", ""),
            events=events,
        )

        # Step 2: decide whether to speak
        candidate = decide_action(candidates)
        self._last_initiative_time = time.time()
        if candidate is None:
            return

        # Step 3: detect character language for initiative prompt
        char = ctx.get("character") or core_state_store.get("character")
        char_lang = "zh"  # default for characters whose primary name is Chinese
        if char is not None:
            name_dict = char.persona.name if hasattr(char, "persona") else {}
            if name_dict.get("ja"):
                char_lang = "ja"
            elif name_dict.get("en"):
                char_lang = "en"
            elif name_dict.get("ko"):
                char_lang = "ko"
            # Only use non-zh if the character actually has that name configured
            # (if the only name is zh, stays "zh" by default)

        # Step 4: build structured initiative prompt from intent
        prompt = build_initiative_prompt(
            candidate["type"], candidate["topic"],
            activity=ctx.get("activity", ""),
            app_name=ctx.get("context", ""),
            language=char_lang,
        )

        # Step 4: dispatch through Runtime pipeline
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self._dispatch_initiative(prompt))
            else:
                loop.run_until_complete(self._dispatch_initiative(prompt))
        except RuntimeError:
            # No running loop — create one
            asyncio.run(self._dispatch_initiative(prompt))

    async def _dispatch_initiative(self, prompt: str) -> None:
        """Create and dispatch an INITIATIVE_TRIGGERED event."""
        event = Event(
            type=EventType.INITIATIVE_TRIGGERED,
            payload={"text": prompt},
            source="initiative_checker",
        )
        ctx = await self.dispatch(event)

        if ctx.error or not ctx.reply_text:
            return

        # Track in initiative buffer for closure detection
        from app.core.initiative_buffer import initiative_buffer
        initiative_buffer.push(ctx.reply_text[:80], ctx.reply_text)

    def _init_screen_watcher(self):
        """Initialize ScreenWatcher — background active window monitor.

        Captures foreground window changes and pushes events to the
        initiative queue for the checker to process.
        """
        from app.services.screen_watcher import ScreenWatcher

        self.screen_watcher = ScreenWatcher(interval=5.0)

        def on_screen_change(old: dict, new: dict) -> None:
            app = new.get("app", "").lower()
            # Auto-infer activity from app
            activity = ScreenWatcher._APP_ACTIVITY_MAP.get(app, "idle")
            core_state_store.update(activity=activity, context=app)
            # Push to initiative queue
            initiative_queue.push(
                "screen_change",
                {"from_app": old.get("app", ""), "to_app": new.get("app", ""),
                 "from_title": old.get("title", ""), "to_title": new.get("title", ""),
                 "inferred_activity": activity},
                priority=2,
            )

        self.screen_watcher.on_context_change = on_screen_change
        self.screen_watcher.start()

    def shutdown(self):
        """Gracefully shut down background tasks (memory, initiative, screen, etc.)."""
        # Memory provider shuts down its own ticker + store
        memory_provider = self.providers.get("memory")
        if memory_provider is not None and hasattr(memory_provider, "shutdown"):
            memory_provider.shutdown()
        # Initiative + screen services
        if self.initiative_checker is not None:
            self.initiative_checker.stop()
            self.initiative_checker = None
        if self.screen_watcher is not None:
            self.screen_watcher.stop()
            self.screen_watcher = None
        from app.core.initiative_buffer import initiative_buffer
        initiative_buffer.stop_expiry()

    @staticmethod
    def _fallback_provider(name: str):
        """Return a minimal fallback when no provider is registered."""
        from app.interfaces.llm import LLMResponse

        class _Fallback:
            async def generate(self, *a, **kw): return LLMResponse()
            async def generate_stream(self, *a, **kw): yield ""
            async def synthesize(self, *a, **kw): return b""
            async def speak(self, *a, **kw): return ""
            async def transcribe(self, *a, **kw): return ""
            async def store(self, *a, **kw): pass
            async def retrieve(self, *a, **kw): return []
            async def consolidate(self, *a, **kw): pass
            async def summarize(self, *a, **kw): return ""
            async def forget(self, *a, **kw): return 0
            async def execute(self, *a, **kw): return ""
            async def list_tools(self, *a, **kw): return []
            async def set_expression(self, *a, **kw): pass
            async def set_gesture(self, *a, **kw): pass
        return _Fallback()

    async def dispatch(self, event: Event, status_callback=None) -> Context:
        """Single entry point — all interaction types flow through here.

        Args:
            event: The event to dispatch.
            status_callback: Optional async callable called with status strings
                             during pipeline execution (e.g., tool calls).

        Returns the Context after all pipeline steps have run.
        """
        ctx = Context(event=event, status_callback=status_callback)
        ctx.state["event"] = event

        # Extract user_text from text events
        if event.type == EventType.TEXT_RECEIVED:
            ctx.user_text = event.payload.get("text", "")

        # Initiative events carry a generated prompt as user_text
        if event.type == EventType.INITIATIVE_TRIGGERED:
            ctx.user_text = event.payload.get("text", "")

        # Inject persistent Conversation
        if self.conversation is not None:
            ctx.state["conversation"] = self.conversation

        # Track turn count in state store
        turn_count = state_store.get("turn_count", 0)
        state_store.set("turn_count", turn_count + 1)
        ctx.state["turn_count"] = turn_count + 1

        ctx = await self.pipeline.run(ctx)

        # Notify memory provider for background processing (ticker, etc.)
        memory_provider = self.providers.get("memory")
        if memory_provider is not None and not ctx.error and hasattr(memory_provider, "notify_turn"):
            memory_provider.notify_turn()

        return ctx


# Module-level singleton
runtime = CompanionRuntime()
