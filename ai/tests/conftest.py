from __future__ import annotations

import os
from pathlib import Path


def pytest_configure(config) -> None:
    """Keep runtime turn traces produced by tests out of the live database."""
    base_temp = Path(config.option.basetemp or ".pytest-tmp")
    if not base_temp.is_absolute():
        base_temp = Path.cwd() / base_temp
    os.environ["SOULLINK_TURN_TRACE_DB"] = str(
        base_temp / "runtime" / "turns.db"
    )
