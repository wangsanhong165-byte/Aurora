"""Longest‑common‑prefix (LCP) based text deduplication for pseudo‑streaming ASR.

Each ASR inference returns the *full* recognized text for the current
window.  We only want to emit the *new* suffix that has appeared since
the previous result.
"""

from __future__ import annotations


def longest_common_prefix(a: str, b: str) -> int:
    """Return length of the longest common prefix of two strings."""
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n


class TextDeduper:
    """Maintains the last-seen text and computes incremental diffs.

    Usage::

        d = TextDeduper()
        diff = d.update("abc")        # → ("abc", "")
        diff = d.update("abc def")    # → ("abc def", "def")
    """

    def __init__(self) -> None:
        self._prev: str = ""
        self._full: str = ""

    def update(self, new_text: str) -> tuple[str, str]:
        """Accept new full text; return (full, suffix).

        **full** is the deduplicated accumulated text.
        **suffix** is only the *new* portion (may be empty).
        """
        new_text = new_text.strip()
        if not new_text:
            return self._full, ""

        # If the new text is "behind" the previous, keep the longer one.
        if len(new_text) <= len(self._prev):
            if new_text == self._prev[:len(new_text)]:
                return self._full, ""
            # Major change — reset
            self._prev = new_text
            self._full = new_text
            return self._full, new_text

        # New text is longer — compute diff via LCP
        lcp_len = longest_common_prefix(self._prev, new_text)
        suffix = new_text[lcp_len:].strip()

        self._prev = new_text

        if suffix:
            self._full = self._full[:lcp_len] + new_text[lcp_len:]
            self._full = self._full.strip()

        return self._full, suffix

    def reset(self) -> None:
        """Reset for a new utterance."""
        self._prev = ""
        self._full = ""

    @property
    def full_text(self) -> str:
        return self._full
