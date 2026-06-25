"""Cloud TTS engine — external HTTP API compatible with OpenAI TTS."""

from __future__ import annotations

import os
from typing import Any

import requests

from app.modules.tts.base import BaseTTS
from app.modules.tts.factory import TTSFactory




@TTSFactory.register
class CloudTTS(BaseTTS):
    engine_name = "cloud-tts"

    def __init__(self, config: Any = None, **kwargs: Any) -> None:
        super().__init__()
        self._api_url = ""
        self._api_key = ""
        self._model = "tts-1"
        self._voice = "alloy"
        self._timeout = 60
        if config is not None:
            from app.config_manager import CloudTTSConfig
            if isinstance(config, CloudTTSConfig):
                self._api_url = config.base_url.rstrip("/")
                self._api_key = config.api_key
        # Also check env as fallback
        import os as _os
        self._api_url = self._api_url or _os.environ.get("TTS_API_URL", "").rstrip("/")
        self._api_key = self._api_key or _os.environ.get("TTS_API_KEY", "")

    def synthesize(self, text: str, **options: Any) -> bytes:
        if not self._api_url:
            raise RuntimeError("TTS_API_URL not set (configure in conf.yaml or .env)")
        import os as _os
        import requests
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        headers["Content-Type"] = "application/json"
        payload = {
            "model": options.get("model") or _os.environ.get("TTS_CLOUD_MODEL", self._model),
            "input": text,
            "voice": options.get("voice") or _os.environ.get("TTS_CLOUD_VOICE", self._voice),
            "response_format": "wav",
        }
        timeout_val = float(options.get("timeout") or _os.environ.get("TTS_CLOUD_TIMEOUT", str(self._timeout)))
        r = requests.post(
            f"{self._api_url}/audio/speech",
            json=payload,
            headers=headers,
            timeout=timeout_val,
        )
        r.raise_for_status()
        return r.content
