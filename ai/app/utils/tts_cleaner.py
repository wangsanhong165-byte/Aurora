"""TTS text preprocessor — filter LLM output before sending to TTS engine.

Adapted from Open-LLM-VTuber 1.2.1 utils/tts_preprocessor.py.
Changes: replaced loguru with standard logging, removed translator dependency.
"""

import re
import unicodedata


def tts_filter(
    text: str,
    remove_special_char: bool = True,
    ignore_brackets: bool = True,
    ignore_parentheses: bool = True,
    ignore_asterisks: bool = True,
    ignore_angle_brackets: bool = True,
) -> str:
    """Filter text before TTS generation.

    Args:
        text: Text to filter.
        remove_special_char: Remove non-letter/number/punctuation chars.
        ignore_brackets: Remove text within brackets [...] (including nested).
        ignore_parentheses: Remove text within parentheses (...).
        ignore_asterisks: Remove text within asterisks *...*.
        ignore_angle_brackets: Remove text within angle brackets <...>.

    Returns:
        Filtered text safe for TTS.
    """
    if not text:
        return text

    if ignore_asterisks:
        try:
            text = _filter_asterisks(text)
        except Exception:
            pass

    if ignore_brackets:
        try:
            text = _filter_nested(text, "[", "]")
        except Exception:
            pass

    if ignore_parentheses:
        try:
            text = _filter_nested(text, "(", ")")
        except Exception:
            pass

    if ignore_angle_brackets:
        try:
            text = _filter_nested(text, "<", ">")
        except Exception:
            pass

    if remove_special_char:
        try:
            text = _remove_special_characters(text)
        except Exception:
            pass

    return text.strip()


def _remove_special_characters(text: str) -> str:
    """Remove all non-letter, non-number, and non-punctuation characters."""
    normalized = unicodedata.normalize("NFKC", text)

    def is_valid_char(ch: str) -> bool:
        cat = unicodedata.category(ch)
        return cat.startswith("L") or cat.startswith("N") or cat.startswith("P") or ch.isspace()

    return "".join(ch for ch in normalized if is_valid_char(ch))


def _filter_nested(text: str, left: str, right: str) -> str:
    """Remove text between matching left/right delimiters, handling nesting."""
    if not isinstance(text, str) or not text:
        return text
    result = []
    depth = 0
    for ch in text:
        if ch == left:
            depth += 1
        elif ch == right:
            if depth > 0:
                depth -= 1
        else:
            if depth == 0:
                result.append(ch)
    filtered = "".join(result)
    filtered = re.sub(r"\s+", " ", filtered).strip()
    return filtered


def _filter_asterisks(text: str) -> str:
    """Remove text enclosed within asterisks (*, **, ***, etc.)."""
    filtered = re.sub(r"\*{1,}((?!\*).)*?\*{1,}", "", text)
    return re.sub(r"\s+", " ", filtered).strip()
