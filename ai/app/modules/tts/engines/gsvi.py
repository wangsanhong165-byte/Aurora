"""GSVI (GPT-SoVITS) engine — legacy HTTP API."""

from __future__ import annotations

import os
from typing import Any

import requests

from app.config_manager.service_config import service_config
from app.modules.tts.base import BaseTTS
from app.modules.tts.factory import TTSFactory

_EMOTION_MAP = {
    "default": "默认", "happy": "开心", "sad": "悲伤",
    "angry": "愤怒", "surprise": "惊讶", "fear": "恐惧",
    "neutral": "中性", "calm": "平静", "excited": "激动",
    "serious": "严肃", "gentle": "温柔",
}
_TEXT_LANG_MAP = {
    "zh": "中英混合", "cn": "中英混合", "chinese": "中英混合",
    "mixed": "中英混合", "auto": "中英混合", "zh_en": "中英混合",
    "en": "英文", "english": "英文",
    "ja": "日文", "jp": "日文", "japanese": "日文",
    "ko": "韩文", "kr": "韩文", "korean": "韩文",
    "yue": "粤语", "cantonese": "粤语",
}
_PROMPT_LANG_MAP = {
    "zh": "中文", "cn": "中文", "chinese": "中文",
    "mixed": "中文", "auto": "中文", "zh_en": "中文",
    "en": "英文", "english": "英文",
    "ja": "日文", "jp": "日文", "japanese": "日文",
    "ko": "韩文", "kr": "韩文", "korean": "韩文",
    "yue": "粤语", "cantonese": "粤语",
}


def _map(raw: str, mapping: dict[str, str]) -> str:
    return mapping.get(raw.strip().lower(), raw.strip())


def synthesize(text: str) -> bytes:
    gsvi_url = os.environ.get("GSVI_URL", service_config.url("gsvi")).rstrip("/")
    payload = {
        "model": os.environ.get("GSVI_MODEL", "GSVI-v4"),
        "input": text,
        "voice": os.environ.get("GSVI_VOICE", ""),
        "response_format": "wav",
        "speed": float(os.environ.get("GSVI_SPEED", "1.0")),
        "other_params": {
            "text_lang": os.environ.get("GSVI_TEXT_LANG", "中英混合"),
            "prompt_lang": os.environ.get("GSVI_PROMPT_LANG", "中文"),
            "emotion": os.environ.get("GSVI_EMOTION", "默认"),
        },
    }
    r = requests.post(f"{gsvi_url}/v1/audio/speech", json=payload, timeout=180)
    r.raise_for_status()
    return r.content


@TTSFactory.register
class GSVITTS(BaseTTS):
    engine_name = "gsvi"

    def synthesize(self, text: str, **options: Any) -> bytes:
        return synthesize(text)
