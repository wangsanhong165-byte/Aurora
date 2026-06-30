"""Live2D providers — registered on import."""
from pathlib import Path

from app.interfaces.live2d import Live2DInterface, MockLive2D
from app.providers.registry import provider_registry

provider_registry.register(Live2DInterface, "mock", MockLive2D)

# Resolve config paths relative to this file, not CWD
_LIVE2D_CONFIG = Path(__file__).resolve().parents[3] / "config" / "live2d_models.json"
if _LIVE2D_CONFIG.exists():
    from app.providers.live2d.bridge_provider import BridgeLive2DProvider

    provider_registry.register(Live2DInterface, "bridge", BridgeLive2DProvider)
    provider_registry.register(Live2DInterface, "default", BridgeLive2DProvider)
else:
    provider_registry.register(Live2DInterface, "default", MockLive2D)

# Register Open-LLM-VTuber provider if configured (always, it's opt-in by base_url)
from app.providers.live2d.open_llm_vtuber_provider import OpenLLMVTuberProvider
provider_registry.register(Live2DInterface, "open_llm_vtuber", OpenLLMVTuberProvider)
