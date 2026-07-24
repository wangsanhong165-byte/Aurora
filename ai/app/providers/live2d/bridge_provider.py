"""BridgeLive2DProvider — implements Live2DInterface via bridge WebSocket relay + local audio playback.

Extracts production logic from:
  - AgentLoop._send_live2d_expression()  → POST /live2d/expression
  - TurnRuntime._tts_and_play()          → AsyncAudioPlayer.enqueue()

Architecture:
  set_expression(emotion) = HTTP POST to bridge → relay to all WS clients
  speak(audio, expression) = enqueue audio to local AsyncAudioPlayer for speaker output

This provider is paired with RuntimeWebSocketHandler which independently reads
ctx.audio and ctx.emotion from the pipeline Context and delivers them as JSON
over the WebSocket to the frontend. The handler covers browser playback;
this provider covers local speaker playback + live2d expression relay.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from app.config_manager.service_config import service_config
from app.interfaces.live2d import Live2DInterface
from app.tts.player import AsyncAudioPlayer

logger = logging.getLogger("bridge.live2d_provider")

_BRIDGE_URL: str = os.environ.get(
    "BRIDGE_URL",
    service_config.url("bridge"),
).rstrip("/")


class BridgeLive2DProvider(Live2DInterface):
    """Live2DInterface backed by bridge expression relay + local audio playback.

    Production path:
      set_expression("happy")
        → POST http://127.0.0.1:9528/live2d/expression {"expression": "happy"}
        → bridge relays {"type": "expression", "name": "happy"} to all WS clients

      speak(wav_bytes, "happy")
        → AsyncAudioPlayer.enqueue(wav_bytes, text=...)
        → sounddevice plays through speakers

    Uses asyncio.to_thread for sync bridge calls (same pattern as HTTPTTSProvider).
    """

    def __init__(
        self,
        bridge_url: str | None = None,
        player: AsyncAudioPlayer | None = None,
        skip_expression: bool = False,
    ):
        self._bridge_url = (bridge_url or _BRIDGE_URL).rstrip("/")
        self._player = player or AsyncAudioPlayer()
        self._skip_expression = skip_expression
        self._started = False
        # Auto-start: player must be running before enqueue is called
        self.start()

    # ── lifecycle (mirrors TurnRuntime.start/shutdown) ──────────────────

    def start(self) -> None:
        """Start the audio player background thread."""
        if not self._started:
            self._player.start()
            self._started = True

    def shutdown(self, wait: bool = False) -> None:
        """Stop the audio player."""
        if self._started:
            self._player.shutdown(wait=wait)
            self._started = False

    # ── Live2DInterface ────────────────────────────────────────────────

    async def set_expression(self, emotion: str, intensity: float = 0.5) -> None:
        """Relay an emotion expression to the bridge via HTTP POST.

        Production logic extracted from AgentLoop._send_live2d_expression():
          requests.post("http://127.0.0.1:9528/live2d/expression",
                        json={"expression": tone}, timeout=1.0)
        """
        if self._skip_expression or not emotion:
            return
        try:
            await asyncio.to_thread(
                self._post_expression,
                emotion, intensity,
            )
        except Exception:
            logger.debug("set_expression(%s) failed (bridge may not be running)", emotion)

    def _post_expression(self, emotion: str, intensity: float = 0.5) -> None:
        """Synchronous HTTP POST to bridge — runs in thread pool."""
        import requests
        requests.post(
            f"{self._bridge_url}/live2d/expression",
            json={"expression": emotion, "intensity": intensity},
            timeout=1.0,
        )

    async def set_gesture(self, gesture: str) -> None:
        """Send a gesture command to the Live2D model via the bridge.

        Maps to POST /live2d/gesture on the bridge — the bridge relays
        {"type": "gesture", "name": "<gesture>"} to all WS clients.
        """
        if not gesture or gesture == "none":
            return
        try:
            await asyncio.to_thread(
                self._post_gesture,
                gesture,
            )
        except Exception:
            logger.debug("set_gesture(%s) failed (bridge may not be running)", gesture)

    def _post_gesture(self, gesture: str) -> None:
        """Synchronous HTTP POST to bridge — runs in thread pool."""
        import requests
        requests.post(
            f"{self._bridge_url}/live2d/gesture",
            json={"gesture": gesture},
            timeout=1.0,
        )

    async def speak(self, audio: bytes, expression: str = "") -> None:
        """Play audio locally through the AsyncAudioPlayer.

        Production logic extracted from TurnRuntime._tts_and_play():
          1. wav = self.tts.synthesize(text)     ← already done by TTSStep
          2. self.player.enqueue(wav, text=text)  ← this is what speak() does

        The expression parameter is used for the expression relay BEFORE speaking.
        """
        if not audio:
            return

        # Send expression before speaking (mirrors production flow)
        if expression:
            await self.set_expression(expression)

        # Enqueue for local playback
        await asyncio.to_thread(self._player.enqueue, audio, text=None)

    # ── convenience for turn-level audio playback ──────────────────────

    async def begin_turn(self) -> None:
        """Signal start of a new response turn (player barrier)."""
        await asyncio.to_thread(self._player.begin_turn)

    async def end_turn(self) -> None:
        """Signal end of turn (player barrier)."""
        await asyncio.to_thread(self._player.end_turn)

    async def wait_output_done(self, timeout: float | None = None) -> bool:
        """Wait for all audio to finish playing."""
        return await asyncio.to_thread(self._player.wait_done, timeout)
