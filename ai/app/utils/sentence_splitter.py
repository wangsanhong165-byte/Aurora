"""Sentence splitting utilities - adapted from Open-LLM-VTuber 1.2.1 utils/sentence_divider.py.

Uses pysbd for accurate multi-language sentence segmentation.
Falls back to regex for unsupported languages.
"""

import re
from typing import List, Tuple

try:
    import pysbd
    _HAS_PYSBD = True
except ImportError:
    _HAS_PYSBD = False


def split_sentences(text: str, lang: str = "en") -> List[str]:
    """Split text into sentences. Falls back to regex if pysbd not available."""
    if not _HAS_PYSBD:
        return [s.strip() for s in re.split(r'(?<=[。！？.!?])\s+', text) if s.strip()]
    segmenter = pysbd.Segmenter(language=lang, clean=True)
    return segmenter.segment(text)
