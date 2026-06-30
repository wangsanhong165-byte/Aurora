"""Sentence divider — splits long text into TTS-friendly chunks.

Acts as a fallback when the LLM returns a single long segment without
proper segmentation. Uses punctuation boundaries to split.

Inspired by Open-LLM-VTuber's sentence_divider decorator.
"""

import re
from typing import Optional

# Sentence-ending punctuation for various languages
_SENTENCE_END = re.compile(
    r'[。！？.!?\n]'
    r'|(?<=[.!?])\s+(?=[A-Z\u4e00-\u9fff])'  # EN period + space + uppercase/CJK
)

# Max characters per segment before forced split
_MAX_CHARS = 80


def divide(text: str, max_chars: Optional[int] = None) -> list[str]:
    """Split text into TTS-friendly segments.

    Preserves sentence boundaries; falls back to length-based split when
    a single sentence exceeds max_chars.

    Args:
        text: Input text to split.
        max_chars: Max characters per segment (default 80).

    Returns:
        List of text segments. Empty list if input is empty.
    """
    if not text or not text.strip():
        return []

    max_chars = max_chars or _MAX_CHARS
    text = text.strip()

    # Short text — return as-is
    if len(text) <= max_chars:
        return [text]

    # Split by sentence boundaries
    segments = _split_by_boundary(text)

    # Merge small segments and split oversized ones
    result: list[str] = []
    buffer = ""

    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue

        # If this segment alone exceeds max_chars, force-split it
        if len(seg) > max_chars:
            if buffer:
                result.append(buffer)
                buffer = ""
            result.extend(_force_split(seg, max_chars))
            continue

        # Accumulate into buffer
        if not buffer:
            buffer = seg
        elif len(buffer) + len(seg) + 1 <= max_chars:
            buffer += seg
        else:
            result.append(buffer)
            buffer = seg

    if buffer:
        result.append(buffer)

    return result


def _split_by_boundary(text: str) -> list[str]:
    """Split text at sentence boundaries."""
    segments: list[str] = []
    start = 0

    for match in _SENTENCE_END.finditer(text):
        end = match.end()
        segments.append(text[start:end])
        start = end

    # Remainder
    if start < len(text):
        tail = text[start:].strip()
        if tail:
            segments.append(tail)

    return segments or [text]


def _force_split(text: str, max_chars: int) -> list[str]:
    """Split a long string at the last boundary before max_chars."""
    result: list[str] = []
    remaining = text

    while len(remaining) > max_chars:
        # Try to find last space or punctuation before max_chars
        chunk = remaining[:max_chars]
        split_at = -1

        # Find last good break point (space, comma, etc.)
        for i in range(max_chars - 1, max_chars // 2, -1):
            ch = remaining[i]
            if ch in ' \t，,；;、':
                split_at = i
                break

        if split_at > 0:
            result.append(remaining[:split_at].strip())
            remaining = remaining[split_at:].strip()
        else:
            # No good break — hard split
            result.append(chunk.strip())
            remaining = remaining[max_chars:].strip()

    if remaining:
        result.append(remaining)

    return result
