"""Provider Factory — creates provider instances from the registry.

Includes automatic discovery: imports all known provider packages to
trigger their side-effect registrations. Runtime never needs to import
provider packages directly.
"""

from app.providers.registry import provider_registry


class ProviderFactory:
    """Creates provider instances with dependency injection.

    Usage:
        llm = ProviderFactory.create(LLMInterface, "deepseek", api_key="...")
    """

    _discovered: bool = False

    @classmethod
    def discover(cls) -> None:
        """Import all known provider packages to trigger registration.

        Each provider's __init__.py registers its implementations with
        the global provider_registry as a side effect of import. This
        method explicitly imports every known provider package so that
        Runtime and business logic never need to import them directly.

        Safe to call multiple times — only executes once.
        """
        if cls._discovered:
            return
        cls._discovered = True

        _PROVIDER_PACKAGES = [
            "app.providers.llm",
            "app.providers.tts",
            "app.providers.asr",
            "app.providers.memory",
            "app.providers.tool",
            "app.providers.live2d",
        ]
        for pkg in _PROVIDER_PACKAGES:
            try:
                __import__(pkg)
            except Exception:
                pass  # Skip providers with missing dependencies

    @staticmethod
    def create(interface_type: type, name: str = "default", **kwargs):
        ProviderFactory.discover()
        provider_class = provider_registry.resolve(interface_type, name)
        if provider_class is None:
            raise ValueError(
                f"No provider registered for {interface_type.__name__} name={name!r}. "
                f"Available: {provider_registry.list_providers(interface_type)}"
            )
        return provider_class(**kwargs)
