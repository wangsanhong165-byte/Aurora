"""TTS providers — registered on import."""
import os

from app.interfaces.tts import TTSInterface, MockTTS
from app.providers.registry import provider_registry

provider_registry.register(TTSInterface, "mock", MockTTS)

# Register real provider if TTS service URL is configured; "default" always resolves
tts_url = os.environ.get("TTS_URL") or os.environ.get("TTS_PORT")
if tts_url:
    from app.providers.tts.http_adapter import HTTPTTSProvider

    provider_registry.register(TTSInterface, "http", HTTPTTSProvider)
    provider_registry.register(TTSInterface, "default", HTTPTTSProvider)
else:
    provider_registry.register(TTSInterface, "default", MockTTS)
