"""Memory module — character-agnostic store + per-character compiled memory.

Shared facts (user profile) persist across character changes.
Compiled memory (today/week/longterm/facts.md) is per-character.
"""

from app.memory.store import memory_store, MemoryStore
from app.memory.extractor import run_extraction_pipeline
from app.memory.compiler import (
    get_compiled_memory,
    compile_today_and_assemble,
    compile_and_assemble,
    regenerate_for_character,
    set_llm_adapter as set_compiler_llm,
    set_active_char,
    get_active_char_id,
)
from app.memory.ticker import MemoryTicker

# Global ticker instance
memory_ticker: MemoryTicker | None = None


def get_memory_for_active_char(character_id: str = "") -> str:
    """Get compiled memory for the currently active character."""
    cid = character_id or get_active_char_id()
    return get_compiled_memory(cid)


def create_ticker(llm_adapter=None) -> MemoryTicker:
    global memory_ticker
    ticker = MemoryTicker(llm_adapter)
    memory_ticker = ticker
    return ticker


def on_character_switch(old_id: str, new_id: str):
    """Called when CharacterRegistry fires on_activate.
    
    Regenerates compiled memory for the new character from shared facts,
    then tells the ticker to use the new character context.
    """
    if not new_id:
        return
    print(f"[memory] Character switch: {old_id} -> {new_id}")

    # Update compiler's active character
    set_active_char(new_id)

    # Regenerate compiled memory for new character
    regenerate_for_character(new_id)


def init_memory(llm_adapter=None, character_registry=None):
    """Initialize all memory subsystems. Called at app startup."""
    set_compiler_llm(llm_adapter)
    memory_store.start()

    # Register character switch callback
    if character_registry:
        character_registry.on_activate(on_character_switch)
        # Set initial character
        cid = character_registry.active_id
        if cid:
            set_active_char(cid)
            regenerate_for_character(cid)

    ticker = create_ticker(llm_adapter)
    ticker.start()
    ticker.recover()
    return ticker


def shutdown_memory():
    global memory_ticker
    if memory_ticker:
        memory_ticker.stop()
        memory_ticker = None
    memory_store.stop()
