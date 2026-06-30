"""Provider Registry — singleton for discovering and resolving provider implementations."""

from typing import Type, Any


class ProviderRegistry:
    """Global registry mapping (interface_type, name) -> provider_class.

    Usage:
        provider_registry.register(LLMInterface, "deepseek", DeepSeekProvider)
        provider = provider_registry.resolve(LLMInterface)
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._providers: dict = {}
        return cls._instance

    def register(self, interface_type: type, name: str, provider_class: type) -> None:
        key = (interface_type, name)
        self._providers[key] = provider_class

    def resolve(self, interface_type: type, name: str = "default") -> type | None:
        key = (interface_type, name)
        if key not in self._providers:
            key = (interface_type, "default")
        return self._providers.get(key)

    def list_providers(self, interface_type: type = None) -> list[dict[str, Any]]:
        result = []
        for (iface, name), cls in self._providers.items():
            if interface_type is None or iface is interface_type:
                result.append({"interface": iface.__name__, "name": name, "class": cls.__name__})
        return result


provider_registry = ProviderRegistry()
