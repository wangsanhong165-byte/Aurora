"""TTS providers — registered on import, env read lazily at first use.

Provider constructors read TTS_URL / service_config at init time, so the
.env file just needs to be loaded by the time the first synthesize() call
happens — not at module import time.
"""
from app.interfaces.tts import TTSInterface, MockTTS
from app.providers.registry import provider_registry

provider_registry.register(TTSInterface, "mock", MockTTS)

from app.providers.tts.http_adapter import HTTPTTSProvider

provider_registry.register(TTSInterface, "http", HTTPTTSProvider)
provider_registry.register(TTSInterface, "default", HTTPTTSProvider)
