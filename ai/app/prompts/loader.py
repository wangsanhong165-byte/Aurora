"""Prompt template loader.

Loads `.txt` prompt files from `prompts/utils/` and renders them with
variable substitution. Caches loaded templates for performance.

Usage:
    from app.prompts.loader import render, render_optional

    system = render("identity_ishiki", identity="...", ishiki="...")
    pinned = render_optional("pinned_memories", content="...")
"""

import logging
from functools import cache
from pathlib import Path

logger = logging.getLogger("bridge.prompts")

_PROMPTS_DIR = Path(__file__).resolve().parent / "utils"


@cache
def _load(name: str) -> str:
    """Load a prompt template by name (without .txt extension)."""
    path = _PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        logger.warning("Prompt '%s' not found at %s", name, path)
        return ""
    text = path.read_text("utf-8").strip()
    logger.debug("Loaded prompt '%s' (%d chars)", name, len(text))
    return text


def render(template_name: str, **vars: str) -> str:
    """Load and render a prompt template with variable substitution.

    Args:
        template_name: Template name (filename without .txt).
        **vars: Variables to substitute into {placeholder} slots.

    Returns:
        Rendered string, or empty string if template not found.
    """
    template = _load(template_name)
    if not template:
        return ""
    try:
        return template.format(**vars)
    except KeyError as e:
        logger.warning("Missing variable %s in prompt '%s'", e, template_name)
        return template
    except Exception as e:
        logger.error("Failed to render prompt '%s': %s", template_name, e)
        return template


def render_optional(template_name: str, condition: bool, **vars: str) -> str:
    """Conditionally render a prompt template.

    Returns empty string when condition is False.
    """
    if not condition:
        return ""
    return render(template_name, **vars)


def list_prompts() -> list[str]:
    """List all available prompt template names."""
    if not _PROMPTS_DIR.exists():
        return []
    return sorted(p.stem for p in _PROMPTS_DIR.glob("*.txt"))


def reload_cache() -> None:
    """Clear template cache (e.g. after modifying prompt files at runtime)."""
    _load.cache_clear()
    logger.info("Prompt cache cleared (%d templates)", len(list_prompts()))
