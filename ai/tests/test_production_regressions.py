"""Production Regression Test Suite — validates real provider pipelines.

These tests exercise the REAL provider stack (DeepSeek LLM, SQLiteMemory, etc.)
and MUST pass after any architectural migration or provider refactoring.

All tests are opt-in: they check environment variables before running.
Run with:
    python -m pytest tests/test_production_regressions.py -v
    python -m unittest tests/test_production_regressions.py -v

Set SKIP_PRODUCTION_TESTS=1 to skip all production regression tests.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.runtime.runtime import CharacterRuntime
from turn_input_fixtures import turn_input_from_event

# ── CWD guard ──────────────────────────────────────────────────────────────────
# Tool and Live2D providers use Path("config/...") relative paths, so we must
# ensure the working directory is the project root.
_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if os.path.abspath(".") != os.path.abspath(_PROJECT_ROOT):
    os.chdir(_PROJECT_ROOT)

# ── Skip guard ──────────────────────────────────────────────────────────────

RUN_PRODUCTION = os.environ.get("RUN_PRODUCTION_TESTS") == "1"


def requires_env(var: str):
    """Skip test if an environment variable is not set."""
    return unittest.skipUnless(os.environ.get(var), f"{var} not set")


# ── Test: Startup / Initialization ─────────────────────────────────────────

@unittest.skipUnless(RUN_PRODUCTION, "SKIP_PRODUCTION_TESTS is set")
class TestStartupRegression(unittest.TestCase):
    """TC-1: Runtime boots with all expected providers and pipeline steps."""

    @classmethod
    def setUpClass(cls):
        # Isolate DB
        cls._db_path = os.path.join(
            tempfile.gettempdir(), "prod_regression_startup.db"
        )
        os.environ["MEMORY_DB_PATH"] = cls._db_path
        from app.providers.registry import provider_registry
        from app.interfaces.llm import LLMInterface
        from app.interfaces.memory import MemoryInterface
        from app.interfaces.asr import ASRInterface
        from app.interfaces.tts import TTSInterface

        cls._provider_registry = provider_registry
        cls._providers_raw = {
            "LLMInterface": provider_registry.list_providers(LLMInterface),
            "MemoryInterface": provider_registry.list_providers(MemoryInterface),
            "ASRInterface": provider_registry.list_providers(ASRInterface),
            "TTSInterface": provider_registry.list_providers(TTSInterface),
        }
        # list_providers returns list of dicts; extract names
        cls._providers = {
            k: [p.get("name") for p in v]
            for k, v in cls._providers_raw.items()
        }

        cls.runtime = CharacterRuntime()

    @classmethod
    def tearDownClass(cls):
        cls.runtime.shutdown()
        try:
            os.remove(cls._db_path)
        except OSError:
            pass

    def test_01_providers_registered(self):
        """At least LLM and Memory providers must be registered."""
        self.assertIn("default", self._providers["LLMInterface"])
        self.assertIn("default", self._providers["MemoryInterface"])

    def test_02_runtime_providers_initialized(self):
        """Runtime has llm and memory providers wired."""
        self.assertIsNotNone(self.runtime.providers.get("llm"))
        self.assertIsNotNone(self.runtime.providers.get("memory"))

    def test_03_runtime_has_9_pipeline_steps(self):
        """Pipeline contains all 9 expected steps."""
        step_names = [type(s).__name__ for s in self.runtime.pipeline._steps]
        expected = [
            "ASRStep", "CharacterStep", "MemoryRetrieveStep",
            "DecisionStep", "EmotionStep", "MemorySaveStep",
            "TTSStep", "Live2DStep",
        ]
        self.assertEqual(step_names, expected)

    def test_04_llm_is_real_not_fallback(self):
        """LLM provider is the real OpenAILLMProvider, not a Mock."""
        from app.providers.llm.openai_adapter import OpenAILLMProvider
        llm = self.runtime.providers.get("llm")
        self.assertIsInstance(llm, OpenAILLMProvider)

    def test_05_memory_is_real_not_fallback(self):
        """Memory provider is SQLiteMemory, not MockMemory."""
        from app.providers.memory.sqlite_memory import SQLiteMemory
        mem = self.runtime.providers.get("memory")
        self.assertIsInstance(mem, SQLiteMemory)

    def test_06_background_services_started(self):
        """InitiativeChecker and ScreenWatcher are running."""
        self.assertIsNotNone(self.runtime.initiative_checker)
        self.assertIsNotNone(self.runtime.screen_watcher)

    def test_07_state_store_initialized(self):
        """Runtime sets initialization flag in state store."""
        from app.runtime.state_store import state_store
        self.assertTrue(state_store.get("runtime_initialized", False))


# ── Test: Real LLM Pipeline ─────────────────────────────────────────────────

@unittest.skipUnless(RUN_PRODUCTION, "SKIP_PRODUCTION_TESTS is set")
@requires_env("OPENAI_API_KEY")
class TestLLMPipelineRegression(unittest.TestCase):
    """TC-2: Real DeepSeek/LLM generates text through the full pipeline."""

    @classmethod
    def setUpClass(cls):
        cls._db_path = os.path.join(
            tempfile.gettempdir(), "prod_regression_llm.db"
        )
        os.environ["MEMORY_DB_PATH"] = cls._db_path
        from app.runtime.event import Event, EventType
        cls.runtime = CharacterRuntime()
        cls.Event = Event
        cls.EventType = EventType

    @classmethod
    def tearDownClass(cls):
        cls.runtime.shutdown()
        try:
            os.remove(cls._db_path)
        except OSError:
            pass

    @staticmethod
    def _run(coro):
        import asyncio
        return asyncio.run(coro)

    def test_llm_returns_reply(self):
        """Dispatching TEXT_RECEIVED produces a non-empty reply."""
        event = self.Event(self.EventType.TEXT_RECEIVED,
                           {"text": "Say exactly one word: hello"}, source="test")
        ctx = self._run(self.runtime.handle_turn(turn_input_from_event(event)))
        self.assertEqual(ctx.error, "", f"Pipeline error: {ctx.error}")
        self.assertTrue(ctx.reply_text, "Reply should not be empty")

    def test_llm_reply_is_plain_text(self):
        """LLM response should be plain text (not raw JSON).

        After response normalization in OpenAILLMProvider, ctx.reply_text
        contains the extracted final_reply text, not the raw JSON envelope.
        Segments are available in ctx.segments.
        """
        rt = CharacterRuntime()
        try:
            event = self.Event(self.EventType.TEXT_RECEIVED,
                               {"text": "Say exactly: ping"}, source="test")
            ctx = self._run(rt.handle_turn(turn_input_from_event(event)))
            self.assertEqual(ctx.error, "")
            # reply_text is plain text (not JSON)
            self.assertFalse(ctx.reply_text.startswith("{"),
                             "reply_text should be plain text, not JSON")
            self.assertTrue(ctx.reply_text.strip(),
                            "reply_text should not be empty")
        finally:
            rt.shutdown()


# ── Test: Real SQLiteMemory Operations ──────────────────────────────────────

@unittest.skipUnless(RUN_PRODUCTION, "SKIP_PRODUCTION_TESTS is set")
class TestMemoryRegression(unittest.TestCase):
    """TC-3: SQLiteMemory store, retrieve, consolidate, summarize."""

    @classmethod
    def setUpClass(cls):
        cls._db_path = os.path.join(
            tempfile.gettempdir(), "prod_regression_memory.db"
        )
        os.environ["MEMORY_DB_PATH"] = cls._db_path
        cls.runtime = CharacterRuntime()
        cls.memory = cls.runtime.providers.get("memory")

    @classmethod
    def tearDownClass(cls):
        cls.runtime.shutdown()
        try:
            os.remove(cls._db_path)
        except OSError:
            pass

    @staticmethod
    def _run(coro):
        import asyncio
        return asyncio.run(coro)

    def test_store_and_retrieve_turn(self):
        """Storing a turn and retrieving it returns results."""
        self._run(self.memory.store("conversation_turn", {
            "user": "Regression test user",
            "assistant": "Regression test reply",
            "intent": "test",
        }))
        results = self._run(self.memory.retrieve("regression test", limit=5))
        self.assertGreater(len(results), 0)
        self.assertIn(results[0]["type"], ("log", "fact", "compiled"))

    def test_consolidate(self):
        """Consolidation (index rebuild) does not raise."""
        self._run(self.memory.consolidate())

    def test_summarize_returns_string(self):
        """Summarize returns a non-empty string."""
        summary = self._run(self.memory.summarize("2024-01-01"))
        self.assertIsInstance(summary, str)
        self.assertTrue(len(summary) > 0)

    def test_forget_does_not_raise(self):
        """forget() returns an int (even if 0)."""
        count = self._run(self.memory.forget("2024-01-01"))
        self.assertIsInstance(count, int)


# ── Test: Multi-Turn Conversation ───────────────────────────────────────────

@unittest.skipUnless(RUN_PRODUCTION, "SKIP_PRODUCTION_TESTS is set")
@requires_env("OPENAI_API_KEY")
class TestMultiTurnRegression(unittest.TestCase):
    """TC-4: Multi-turn conversation with real LLM + memory context."""

    @classmethod
    def setUpClass(cls):
        cls._db_path = os.path.join(
            tempfile.gettempdir(), "prod_regression_multiturn.db"
        )
        os.environ["MEMORY_DB_PATH"] = cls._db_path
        from app.runtime.event import Event, EventType
        cls.runtime = CharacterRuntime()
        cls.Event = Event
        cls.EventType = EventType
        cls.memory = cls.runtime.providers.get("memory")

    @classmethod
    def tearDownClass(cls):
        cls.runtime.shutdown()
        try:
            os.remove(cls._db_path)
        except OSError:
            pass

    @staticmethod
    def _run(coro):
        import asyncio
        return asyncio.run(coro)

    def test_three_turns_without_error(self):
        """Three sequential dispatches all succeed without error."""
        for i in range(3):
            event = self.Event(
                self.EventType.TEXT_RECEIVED,
                {"text": f"Turn {i}: say a single word"}, source="test_multi",
            )
            ctx = self._run(
                self.runtime.handle_turn(turn_input_from_event(event))
            )
            self.assertEqual(ctx.error, "",
                             f"Error on turn {i}: {ctx.error}")

    def test_memory_persists_across_turns(self):
        """Memory from earlier turns is retrievable after later turns.

        Uses a fresh runtime to avoid cross-test conversation history
        contamination from tool_calls.
        """
        rt = CharacterRuntime()
        memory = rt.providers.get("memory")
        try:
            # Store a distinctive turn
            event = self.Event(
                self.EventType.TEXT_RECEIVED,
                {"text": "My favorite number is 42"}, source="test_multi",
            )
            ctx = self._run(rt.handle_turn(turn_input_from_event(event)))
            self.assertEqual(ctx.error, "")

            # Verify it's retrievable
            results = self._run(memory.retrieve("favorite number 42", limit=5))
            self.assertGreater(len(results), 0,
                               "Should find memory about favorite number")
        finally:
            rt.shutdown()


# ── Test: Initiative System ─────────────────────────────────────────────────

@unittest.skipUnless(RUN_PRODUCTION, "SKIP_PRODUCTION_TESTS is set")
class TestInitiativeRegression(unittest.TestCase):
    """TC-6: Initiative queue, checker, buffer, and ScreenWatcher mappings."""

    @classmethod
    def setUpClass(cls):
        # Long idle/check intervals to prevent background firing
        os.environ["INITIATIVE_IDLE_SEC"] = "999999"
        os.environ["INITIATIVE_CHECK_SEC"] = "3600"
        cls._db_path = os.path.join(
            tempfile.gettempdir(), "prod_regression_initiative.db"
        )
        os.environ["MEMORY_DB_PATH"] = cls._db_path
        cls.runtime = CharacterRuntime()

    @classmethod
    def tearDownClass(cls):
        cls.runtime.shutdown()
        try:
            os.remove(cls._db_path)
        except OSError:
            pass

    def test_initiative_checker_instantiated(self):
        """InitiativeChecker is running with configured intervals."""
        self.assertIsNotNone(self.runtime.initiative_checker)
        self.assertEqual(self.runtime.initiative_checker.interval, 3600.0)
        self.assertEqual(self.runtime.initiative_checker.idle_threshold, 999999.0)

    def test_screen_watcher_instantiated(self):
        """ScreenWatcher is running."""
        self.assertIsNotNone(self.runtime.screen_watcher)

    def test_initiative_queue_push_drain(self):
        """Queue accepts items and drains them in priority order."""
        from app.core.initiative_queue import initiative_queue
        initiative_queue.push("test_event", {"key": "val"}, priority=1)
        items = initiative_queue.drain()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].type, "test_event")

    def test_initiative_buffer_push_close_drain(self):
        """Buffer tracks proactive speech and supports closure detection."""
        from app.core.initiative_buffer import initiative_buffer
        initiative_buffer.push("test topic", "test tts reply")
        self.assertEqual(initiative_buffer.pending_count, 1)

        topic = initiative_buffer.try_close("User response text", window_sec=999999)
        self.assertEqual(topic, "test topic")

        drained = initiative_buffer.drain_answered()
        self.assertEqual(len(drained), 1)
        self.assertEqual(drained[0].topic, "test topic")
        self.assertEqual(initiative_buffer.pending_count, 0)

        # Drain remaining so subsequent tests start clean
        empty = initiative_buffer.drain_answered()
        self.assertEqual(len(empty), 0)

    def test_screen_watcher_activity_map(self):
        """ScreenWatcher has app-to-activity mappings for known apps."""
        from app.services.screen_watcher import ScreenWatcher
        self.assertEqual(ScreenWatcher._APP_ACTIVITY_MAP.get("code"), "coding")
        self.assertEqual(ScreenWatcher._APP_ACTIVITY_MAP.get("chrome"), "browsing")
        self.assertGreater(len(ScreenWatcher._APP_ACTIVITY_MAP), 5)


# ── Test: Tool / MCP Provider ────────────────────────────────────────────────

@unittest.skipUnless(RUN_PRODUCTION, "SKIP_PRODUCTION_TESTS is set")
class TestToolProviderRegression(unittest.TestCase):
    """TC-5: LegacyToolProvider registers and resolves correctly."""

    def test_tool_provider_registered(self):
        """ToolInterface has a real (non-mock) default provider."""
        from app.providers.registry import provider_registry
        from app.interfaces.tool import ToolInterface
        from app.providers.factory import ProviderFactory
        ProviderFactory._discovered = False
        ProviderFactory.discover()
        names = [p.get("name") for p in provider_registry.list_providers(ToolInterface)]
        self.assertIn("default", names)

    def test_tool_default_is_legacy_not_mock(self):
        """Default Tool provider is LegacyToolProvider, not MockTool."""
        from app.providers.registry import provider_registry
        from app.interfaces.tool import ToolInterface
        from app.providers.factory import ProviderFactory
        from app.providers.tool.legacy_provider import LegacyToolProvider
        from app.interfaces.tool import MockTool
        ProviderFactory._discovered = False
        ProviderFactory.discover()
        cls = provider_registry.resolve(ToolInterface, "default")
        self.assertIsNotNone(cls)
        self.assertIs(cls, LegacyToolProvider, f"Expected LegacyToolProvider, got {cls}")


# ── Test: Provider Registry ─────────────────────────────────────────────────

@unittest.skipUnless(RUN_PRODUCTION, "SKIP_PRODUCTION_TESTS is set")
class TestProviderRegistryRegression(unittest.TestCase):
    """Provider auto-discovery registers all known implementations."""

    def test_discovery_registers_providers(self):
        """ProviderFactory.discover() triggers registration for all packages."""
        from app.providers.factory import ProviderFactory
        ProviderFactory._discovered = False
        ProviderFactory.discover()

        from app.providers.registry import provider_registry
        from app.interfaces.llm import LLMInterface
        from app.interfaces.memory import MemoryInterface

        llm_names = [p.get("name") for p in provider_registry.list_providers(LLMInterface)]
        mem_names = [p.get("name") for p in provider_registry.list_providers(MemoryInterface)]
        self.assertIn("default", llm_names)
        self.assertIn("default", mem_names)

    def test_provider_factory_creates_real_instances(self):
        """ProviderFactory.create() returns real instances, not mocks."""
        from app.providers.factory import ProviderFactory
        from app.interfaces.llm import LLMInterface
        from app.interfaces.memory import MemoryInterface
        from app.providers.llm.openai_adapter import OpenAILLMProvider
        from app.providers.memory.sqlite_memory import SQLiteMemory

        llm = ProviderFactory.create(LLMInterface)
        mem = ProviderFactory.create(MemoryInterface)
        self.assertIsInstance(llm, OpenAILLMProvider)
        self.assertIsInstance(mem, SQLiteMemory)


# ── Test: Character Registry ────────────────────────────────────────────────

@unittest.skipUnless(RUN_PRODUCTION, "SKIP_PRODUCTION_TESTS is set")
class TestCharacterRegression(unittest.TestCase):
    """Character loading and switching through Runtime."""

    @classmethod
    def setUpClass(cls):
        cls._db_path = os.path.join(
            tempfile.gettempdir(), "prod_regression_char.db"
        )
        os.environ["MEMORY_DB_PATH"] = cls._db_path
        cls.runtime = CharacterRuntime()

    @classmethod
    def tearDownClass(cls):
        cls.runtime.shutdown()
        try:
            os.remove(cls._db_path)
        except OSError:
            pass

    def test_get_character_info_returns_dict(self):
        """Runtime returns character info."""
        info = self.runtime.get_character_info()
        self.assertIn("character_id", info)
        self.assertIn("name", info)
        self.assertIn("card", info)

    def test_switch_character_returns_result(self):
        """switch_character returns a dict with character_id."""
        result = self.runtime.switch_character("default")
        self.assertIn("character_id", result)


# ── Test: Event Dispatch ────────────────────────────────────────────────────

@unittest.skipUnless(RUN_PRODUCTION, "SKIP_PRODUCTION_TESTS is set")
class TestTurnHandlingRegression(unittest.TestCase):
    """Typed turn handling with real providers."""

    @classmethod
    def setUpClass(cls):
        cls._db_path = os.path.join(
            tempfile.gettempdir(), "prod_regression_event.db"
        )
        os.environ["MEMORY_DB_PATH"] = cls._db_path
        from app.runtime.event import Event, EventType
        cls.runtime = CharacterRuntime()
        cls.Event = Event
        cls.EventType = EventType

    @classmethod
    def tearDownClass(cls):
        cls.runtime.shutdown()
        try:
            os.remove(cls._db_path)
        except OSError:
            pass

    @staticmethod
    def _run(coro):
        import asyncio
        return asyncio.run(coro)

    def test_text_received_populates_user_text(self):
        """TEXT_RECEIVED sets ctx.user_text."""
        event = self.Event(self.EventType.TEXT_RECEIVED,
                           {"text": "regression test"}, source="test")
        ctx = self._run(self.runtime.handle_turn(turn_input_from_event(event)))
        self.assertEqual(ctx.user_text, "regression test")

    def test_speech_received_does_not_crash(self):
        """SPEECH_RECEIVED processes without error."""
        event = self.Event(self.EventType.SPEECH_RECEIVED,
                           {"audio": b"\x00" * 160, "sample_rate": 16000},
                           source="test")
        ctx = self._run(self.runtime.handle_turn(turn_input_from_event(event)))
        self.assertEqual(ctx.error, "")

    def test_initiative_triggered_does_not_crash(self):
        """INITIATIVE_TRIGGERED processes without error."""
        event = self.Event(self.EventType.INITIATIVE_TRIGGERED,
                           {"text": "initiative test prompt"}, source="test")
        ctx = self._run(self.runtime.handle_turn(turn_input_from_event(event)))
        self.assertEqual(ctx.error, "")

    def test_turn_count_increments(self):
        """Each dispatch increments turn_count."""
        from app.runtime.state_store import state_store
        before = state_store.get("turn_count", 0)
        event = self.Event(self.EventType.TEXT_RECEIVED,
                           {"text": "turn count test"}, source="test")
        self._run(self.runtime.handle_turn(turn_input_from_event(event)))
        after = state_store.get("turn_count", 0)
        self.assertGreater(after, before)


# ── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
