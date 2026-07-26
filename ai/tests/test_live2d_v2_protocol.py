"""Regression tests for the V2 Live2D presentation handoff."""

import asyncio
import unittest

from starlette.responses import FileResponse

from app.bridge.server import serve_libs
from app.runtime.character_turn import CharacterTurn, TurnInput
from app.runtime.steps.live2d_step import Live2DStep
from app.transport.emitter import TransportEmitter


def _run(coro):
    return asyncio.run(coro)


class TestLive2DV2Protocol(unittest.TestCase):
    def test_cubism_core_library_is_served_from_frontend_assets(self):
        response = _run(serve_libs("live2dcubismcore.min.js"))

        self.assertIsInstance(response, FileResponse)
        self.assertTrue(response.path.endswith("live2dcubismcore.min.js"))

    def test_live2d_step_records_presentation_intent_without_provider_io(self):
        ctx = CharacterTurn(input=TurnInput(text="hello"))
        ctx.emotion = "happy"
        ctx.emotion_intensity = 0.8
        ctx.segments = [{"gesture": "wave"}]

        _run(Live2DStep().run(ctx))

        self.assertEqual(ctx.live2d_intent["emotion"], "happy")
        self.assertEqual(ctx.live2d_intent["behavior"], "wave")
        self.assertEqual(ctx.live2d_intent["speaking"], False)

    def test_emitter_maps_runtime_intent_to_one_semantic_character_update(self):
        ctx = CharacterTurn(input=TurnInput(text="hello"))
        ctx.audio = b"wav"
        ctx.live2d_intent = {
            "emotion": "happy",
            "intensity": 0.8,
            "gesture": "wave",
            "speaking": True,
        }
        update = [
            message for message in TransportEmitter().emit(ctx)
            if message.type == "character_update"
        ][0]

        self.assertEqual(update.type, "character_update")
        self.assertEqual(update.emotion, "happy")
        self.assertEqual(update.behavior, "wave")
        self.assertFalse(hasattr(update, "model_id"))
        self.assertFalse(hasattr(update, "expression"))
        self.assertFalse(hasattr(update, "motion"))
        self.assertTrue(update.speaking)

    def test_spoken_reply_gets_semantic_speak_fallback_instead_of_idle(self):
        ctx = CharacterTurn(input=TurnInput(text="hello"))
        ctx.reply_text = "A normal spoken answer"
        ctx.segments = [{"emotion": "happy", "behavior": "idle", "intensity": 0.8}]

        _run(Live2DStep().run(ctx))

        self.assertEqual(ctx.live2d_intent["behavior"], "speak")
        self.assertEqual(ctx.live2d_intent["emotion"], "happy")
