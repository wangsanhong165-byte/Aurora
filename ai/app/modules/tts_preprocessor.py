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
_RE_THINK_BLOCK = re.compile(r"<think(?:ing)?\b[^>]*>.*?</think(?:ing)?\s*>", re.IGNORECASE | re.DOTALL)
_RE_UNCLOSED_THINK = re.compile(r"<think(?:ing)?\b[^>]*>.*$", re.IGNORECASE | re.DOTALL)
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


def split_reasoning(text: str) -> tuple[str, str]:
    """Split model-private ``<think>`` content from the visible reply."""
    if not text:
        return "", ""
    thoughts: list[str] = []

    def collect(match: re.Match[str]) -> str:
        body = re.sub(r"^<think(?:ing)?\b[^>]*>|</think(?:ing)?\s*>$", "", match.group(0), flags=re.IGNORECASE)
        if body.strip():
            thoughts.append(body.strip())
        return ""

    visible = _RE_THINK_BLOCK.sub(collect, text)
    open_match = _RE_UNCLOSED_THINK.search(visible)
    if open_match:
        body = re.sub(r"^<think(?:ing)?\b[^>]*>", "", open_match.group(0), flags=re.IGNORECASE)
        if body.strip():
            thoughts.append(body.strip())
        visible = visible[:open_match.start()]
    return _RE_SPACES.sub(" ", visible).strip(), "\n\n".join(thoughts)


def clean_for_display(text: str) -> str:
    """Return only the final reply suitable for normal display and speech."""
    return split_reasoning(text)[0]


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
