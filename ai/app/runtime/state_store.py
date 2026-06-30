"""Backward-compatible re-export of StateStore from app.core.state_store.

Moved to app.core.state_store to break the circular import chain.
All new code should import directly from app.core.state_store.
"""

from app.core.state_store import StateStore, state_store  # noqa: F401
