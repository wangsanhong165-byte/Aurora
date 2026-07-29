"""Regression tests for the Live2D presentation handoff."""

import asyncio
import unittest

from starlette.responses import FileResponse

from app.bridge.server import serve_libs
from app.runtime.character_turn import CharacterTurn, TurnInput
from app.runtime.steps.live2d_step import Live2DStep
from app.transport.emitter import TransportEmitter


def _run(coro):
    return asyncio.run(coro)


class TestLive2DV3Handoff(unittest.TestCase):
    def test_cubism_core_library_is_served_from_frontend_assets(self):
        response = _run(serve_libs("live2dcubismcore.min.js"))

        self.assertIsInstance(response, FileResponse)
        self.assertTrue(response.path.endswith("live2dcubismcore.min.js"))

    def test_live2d_step_records_presentation_intent_without_provider_io(self):
        ctx = CharacterTurn(input=TurnInput(text="hello"))
        ctx.emotion = "happy"
        ctx.emotion_intensity = 0.8
        ctx.segments = [{"behavior": "wave"}]

        _run(Live2DStep().run(ctx))

        self.assertEqual(ctx.live2d_intent["emotion"], "happy")
        self.assertEqual(ctx.live2d_intent["behavior"], "wave")
        self.assertEqual(ctx.live2d_intent["speaking"], False)

    def test_emitter_maps_runtime_intent_to_one_semantic_character_event(self):
        ctx = CharacterTurn(input=TurnInput(text="hello"))
        ctx.audio = b"wav"
        ctx.live2d_intent = {
            "emotion": "happy",
            "intensity": 0.8,
            "behavior": "wave",
            "speaking": True,
        }
        update = [
            message for message in TransportEmitter().emit(ctx)
            if message.event_type == "character.intent"
        ][0]

        self.assertEqual(update.event_type, "character.intent")
        self.assertEqual(update.payload.emotion, "happy")
        self.assertEqual(update.payload.behavior, "wave")
        self.assertFalse(hasattr(update.payload, "model_id"))
        self.assertFalse(hasattr(update.payload, "expression"))
        self.assertFalse(hasattr(update.payload, "motion"))

    def test_spoken_reply_gets_semantic_speak_fallback_instead_of_idle(self):
        ctx = CharacterTurn(input=TurnInput(text="hello"))
        ctx.reply_text = "A normal spoken answer"
        ctx.segments = [{"emotion": "happy", "behavior": "idle", "intensity": 0.8}]

        _run(Live2DStep().run(ctx))

        self.assertEqual(ctx.live2d_intent["behavior"], "speak")
        self.assertEqual(ctx.live2d_intent["emotion"], "happy")
