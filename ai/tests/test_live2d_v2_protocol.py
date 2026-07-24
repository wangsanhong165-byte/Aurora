"""Regression tests for the V2 Live2D presentation handoff."""

import asyncio
import unittest

from app.runtime.context import Context
from app.runtime.event import Event, EventType
from app.runtime.steps.live2d_step import Live2DStep
from app.transport.websocket.handler import RuntimeEventHandler


def _run(coro):
    return asyncio.run(coro)


class TestLive2DV2Protocol(unittest.TestCase):
    def test_live2d_step_records_presentation_intent_without_provider_io(self):
        ctx = Context(event=Event(EventType.TEXT_RECEIVED, {"text": "hello"}))
        ctx.emotion = "happy"
        ctx.emotion_intensity = 0.8
        ctx.segments = [{"gesture": "wave"}]

        _run(Live2DStep().run(ctx))

        self.assertEqual(ctx.live2d_intent["emotion"], "happy")
        self.assertEqual(ctx.live2d_intent["gesture"], "wave")
        self.assertEqual(ctx.live2d_intent["speaking"], False)

    def test_handler_maps_runtime_intent_to_one_character_update(self):
        ctx = Context(event=Event(EventType.TEXT_RECEIVED, {"text": "hello"}))
        ctx.audio = b"wav"
        ctx.live2d_intent = {
            "emotion": "happy",
            "intensity": 0.8,
            "gesture": "wave",
            "speaking": True,
        }
        handler = RuntimeEventHandler(
            runtime=object(),
            live2d_mapper=lambda intent: {
                "model_id": "demo",
                "expression": "joy",
                "motion": intent["gesture"],
            },
        )

        update = handler._character_update(ctx)

        self.assertEqual(update.type, "character_update")
        self.assertEqual(update.model_id, "demo")
        self.assertEqual(update.expression, "joy")
        self.assertEqual(update.motion, "wave")
        self.assertTrue(update.speaking)

    def test_spoken_reply_gets_semantic_speak_fallback_instead_of_idle(self):
        ctx = Context(event=Event(EventType.TEXT_RECEIVED, {"text": "hello"}))
        ctx.reply_text = "A normal spoken answer"
        ctx.segments = [{"emotion": "happy", "behavior": "idle", "intensity": 0.8}]

        _run(Live2DStep().run(ctx))

        self.assertEqual(ctx.live2d_intent["behavior"], "speak")
        self.assertEqual(ctx.live2d_intent["emotion"], "happy")
