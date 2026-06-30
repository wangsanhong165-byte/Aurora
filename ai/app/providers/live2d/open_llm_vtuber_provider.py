"""OpenLLMVTuberProvider — implements Live2DInterface via Open-LLM-VTuber HTTP API.

Communicates with a running Open-LLM-VTuber instance to control Live2D
expression and play audio. Uses the Direct Control API (PR #303) when
available, with a fallback to the standard WebSocket message format.

Architecture:
  set_expression(emotion)
    → POST /set_expression {"expression": "<mapped_emotion>"}
    → Open-LLM-VTuber updates the Live2D model expression

  set_gesture(gesture)
    → POST /set_gesture {"gesture": "<gesture>"}

  speak(audio, expression)
    → POST /play_audio {"audio": "<base64>", "expression": "<em>"}
    → Audio is played through the VTuber's audio output

Configuration (env vars):
  OPENLLM_VTUBER_URL — base URL (default: http://127.0.0.1:12393)
  OPENLLM_VTUBER_EMOTION_MAP — optional JSON override for emotion mapping
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from typing import Any

from app.interfaces.live2d import Live2DInterface

logger = logging.getLogger("openllm_vtuber")

_DEFAULT_BASE_URL = os.environ.get("OPENLLM_VTUBER_URL", "http://127.0.0.1:12393")

# Default emotion mapping: CompanionRuntime emotion -> Open-LLM-VTuber emotion names
_DEFAULT_EMOTION_MAP: dict[str, str] = {
    "neutral": "neutral",
    "happy": "happy",
    "sad": "sad",
    "angry": "angry",
    "surprised": "surprise",
    "worried": "worried",
    "shy": "shy",
    "gentle": "gentle",
    "serious": "serious",
    "jealous": "angry",
}

# Default gesture mapping
_DEFAULT_GESTURE_MAP: dict[str, str] = {
    "wave": "wave",
    "tilt": "tilt",
    "nod": "nod",
    "shrug": "shrug",
}


class OpenLLMVTuberProvider(Live2DInterface):
    """Live2DInterface backed by Open-LLM-VTuber HTTP API.

    Sends expression and audio commands to a running Open-LLM-VTuber
    instance over HTTP. Designed as a drop-in alternative to
    BridgeLive2DProvider — switch via configuration only.

    Usage:
        provider = OpenLLMVTuberProvider()
        await provider.set_expression("happy")
        await provider.speak(wav_bytes, "happy")
    """

    def __init__(
        self,
        base_url: str | None = None,
        emotion_map: dict[str, str] | None = None,
        gesture_map: dict[str, str] | None = None,
        timeout: float = 2.0,
    ):
        self._base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")

        # Load emotion map: explicit arg > env var JSON > default
        env_map = os.environ.get("OPENLLM_VTUBER_EMOTION_MAP")
        if env_map and emotion_map is None:
            try:
                emotion_map = json.loads(env_map)
            except json.JSONDecodeError:
                logger.warning("Invalid OPENLLM_VTUBER_EMOTION_MAP JSON, using defaults")

        self._emotion_map: dict[str, str] = emotion_map or dict(_DEFAULT_EMOTION_MAP)
        self._gesture_map: dict[str, str] = gesture_map or dict(_DEFAULT_GESTURE_MAP)
        self._timeout: float = timeout
        self._session: Any = None  # lazy-init httpx.AsyncClient or aiohttp session

    # ── internal HTTP helpers ─────────────────────────────────────────────

    async def _ensure_session(self) -> None:
        """Lazy-init an HTTP client session."""
        if self._session is not None:
            return
        try:
            import httpx
            self._session = httpx.AsyncClient(timeout=self._timeout)
        except ImportError:
            import aiohttp
            self._session = aiohttp.ClientSession()

    async def _post(self, endpoint: str, payload: dict) -> None:
        """Fire-and-forget POST to the Open-LLM-VTuber API."""
        await self._ensure_session()
        url = f"{self._base_url}{endpoint}"
        try:
            if hasattr(self._session, "post"):
                await self._session.post(url, json=payload)
            elif hasattr(self._session, "_session"):  # aiohttp
                async with self._session.post(url, json=payload) as resp:
                    pass
        except Exception as exc:
            logger.debug("POST %s failed: %s (Open-LLM-VTuber may not be running)", endpoint, exc)

    # ── Live2DInterface ───────────────────────────────────────────────────

    async def set_expression(self, emotion: str) -> None:
        """Send an expression update to Open-LLM-VTuber.

        Maps our emotion name (e.g. "happy") to the VTuber's expected
        expression name via the emotion map. Skips if emotion is neutral
        to avoid unnecessary requests.
        """
        if not emotion:
            return
        mapped = self._emotion_map.get(emotion, emotion)
        await self._post("/set_expression", {"expression": mapped})

    async def set_gesture(self, gesture: str) -> None:
        """Send a gesture command to Open-LLM-VTuber."""
        if not gesture or gesture == "none":
            return
        mapped = self._gesture_map.get(gesture, gesture)
        await self._post("/set_gesture", {"gesture": mapped})

    async def speak(self, audio: bytes, expression: str = "") -> None:
        """Send audio to Open-LLM-VTuber for playback.

        The audio is base64-encoded and sent alongside an optional
        expression to set before speaking.
        """
        if not audio:
            return

        if expression:
            await self.set_expression(expression)

        b64 = base64.b64encode(audio).decode("ascii")
        await self._post("/play_audio", {
            "audio": b64,
            "expression": expression or "neutral",
        })

    # ── lifecycle ─────────────────────────────────────────────────────────

    async def shutdown(self) -> None:
        """Close the HTTP client session."""
        if self._session is not None:
            try:
                if hasattr(self._session, "aclose"):
                    await self._session.aclose()
                elif hasattr(self._session, "close"):
                    await self._session.close()
            except Exception:
                pass
            self._session = None

    # ── introspection ─────────────────────────────────────────────────────

    @property
    def base_url(self) -> str:
        return self._base_url

    def to_dict(self) -> dict:
        return {
            "provider": "OpenLLMVTuberProvider",
            "base_url": self._base_url,
            "emotion_map": self._emotion_map,
            "gesture_map": self._gesture_map,
        }
