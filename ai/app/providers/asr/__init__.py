"""ASR providers — registered on import, env read lazily at first use.

Provider constructors read ASR_URL / service_config at init time, so the
.env file just needs to be loaded by the time the first transcribe() call
happens — not at module import time.
"""
from app.interfaces.asr import ASRInterface, MockASR
from app.providers.registry import provider_registry

provider_registry.register(ASRInterface, "mock", MockASR)

from app.providers.asr.http_adapter import HTTPASRProvider

provider_registry.register(ASRInterface, "http", HTTPASRProvider)
provider_registry.register(ASRInterface, "default", HTTPASRProvider)
