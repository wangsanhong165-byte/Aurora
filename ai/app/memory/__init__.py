"""Memory module — character-agnostic store + per-character compiled memory.

Facts, conversation rows, dynamic state, and compiled files are all scoped to
one explicit character. Legacy empty-scope rows are claimed once at startup.
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
def on_character_switch(old_id: str, new_id: str):
    """Update the compatibility active ID when a registry callback is used.

    The provider owns asynchronous regeneration; this callback deliberately
    performs no compilation so a switch cannot trigger the same work twice.
    """
    if not new_id:
        return
    # Update compiler's active character
    set_active_char(new_id)
