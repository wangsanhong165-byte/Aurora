"""TTS Preprocessor — strips markup from text before TTS synthesis.

Borrowed from Open-LLM-VTuber's tts_preprocessor.py pattern:
strips brackets, parentheses, asterisks, and angle brackets from text
so the TTS engine only receives clean, speakable content.

The original (unfiltered) text is still sent to the frontend for display.
"""

import re

# Match content between matching delimiters (non-greedy, handles nesting)
_RE_BRACKETS = re.compile(r"\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]")
# ASCII () and full-width CJK （）
_RE_PARENS = re.compile(r"[（(][^（）()]*(?:[（(][^（）()]*[）)][^（）()]*)*[）)]")
_RE_ASTERISKS = re.compile(r"\*[^*]*(?:\*[^*]*\*[^*]*)*\*")
_RE_ANGLE = re.compile(r"<[^<>]*(?:<[^<>]*>[^<>]*)*>")
# Multiple consecutive spaces
_RE_SPACES = re.compile(r" {2,}")


def strip_brackets(text: str) -> str:
    """Remove [...] and their contents (emotion tags like [joy])."""
    return _RE_BRACKETS.sub("", text)


def strip_parentheses(text: str) -> str:
    """Remove (...) and their contents (action descriptions like (sighs))."""
    return _RE_PARENS.sub("", text)


def strip_asterisks(text: str) -> str:
    """Remove *...* and their contents (action descriptions like *sighs*)."""
    return _RE_ASTERISKS.sub("", text)


def strip_angle_brackets(text: str) -> str:
    """Remove <...> and their contents (think tags, HTML remnants)."""
    return _RE_ANGLE.sub("", text)


def clean_for_tts(text: str) -> str:
    """Remove all markup from text so it's clean for TTS synthesis.

    Applies all filters in order: brackets → parentheses → asterisks
    → angle brackets → collapse spaces → strip.

    Args:
        text: Raw text possibly containing markup.

    Returns:
        Clean text suitable for TTS.
    """
    if not text:
        return ""
    result = strip_brackets(text)
    result = strip_parentheses(result)
    result = strip_asterisks(result)
    result = strip_angle_brackets(result)
    result = _RE_SPACES.sub(" ", result)
    return result.strip()


def extract_emotion_tags(text: str) -> list[str]:
    """Extract emotion keywords from [keyword] tags in text.

    Useful as a fallback tone detector — if the LLM embeds [joy] in
    the display text, we can extract it for Live2D expression.

    Returns:
        List of emotion names found, in order of appearance.
    """
    if not text:
        return []
    return re.findall(r"\[(\w+)\]", text)
