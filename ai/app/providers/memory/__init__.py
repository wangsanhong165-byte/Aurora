"""Memory providers — registered on import."""
from app.interfaces.memory import MemoryInterface, MockMemory
from app.providers.registry import provider_registry
from app.providers.memory.sqlite_memory import SQLiteMemory

provider_registry.register(MemoryInterface, "mock", MockMemory)
provider_registry.register(MemoryInterface, "sqlite", SQLiteMemory)
provider_registry.register(MemoryInterface, "default", SQLiteMemory)
