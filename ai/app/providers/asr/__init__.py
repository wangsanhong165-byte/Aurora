"""ASR providers — registered on import."""
import os

from app.interfaces.asr import ASRInterface, MockASR
from app.providers.registry import provider_registry

provider_registry.register(ASRInterface, "mock", MockASR)

# Register real provider if ASR service URL is configured; "default" always resolves
asr_url = os.environ.get("ASR_URL") or os.environ.get("ASR_PORT")
if asr_url:
    from app.providers.asr.http_adapter import HTTPASRProvider

    provider_registry.register(ASRInterface, "http", HTTPASRProvider)
    provider_registry.register(ASRInterface, "default", HTTPASRProvider)
else:
    provider_registry.register(ASRInterface, "default", MockASR)
