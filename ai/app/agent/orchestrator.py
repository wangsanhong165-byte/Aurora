"""Pipeline orchestrator: ASR → Memory → LLM(stream via service) → SentenceBuffer → TTS → Player.

Two modes:
- ``run_turn()`` — legacy synchronous (backward compatible)
- ``run_turn_streaming()`` — low‑latency: streams LLM tokens via LLM service SSE,
  buffers sentences, calls TTS per‑sentence, enqueues to async player.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Iterator, Optional

import requests

from app.memory.short_term import ShortTermMemory
from app.memory.summarizer import Summarizer
from app.tts.player import AsyncAudioPlayer


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


_SENTENCE_END = re.compile(r"[。，！？!?；;\n]")


def _split_sentences(
    tokens: Iterator[str],
    min_length: int = 5,
    max_length: int = 50,
) -> Generator[str, None, None]:
    buf: list[str] = []
    length = 0

    for token in tokens:
        if not token:
            continue
        buf.append(token)
        length += len(token)

        text = "".join(buf)
        m = _SENTENCE_END.search(text)
        if m:
            end = m.end()
            sentence = text[:end].strip()
            remainder = text[end:].lstrip()
            if len(sentence) >= min_length:
                yield sentence
                buf = [remainder] if remainder else []
                length = len(remainder)
        elif length >= max_length:
            sentence = text.strip()
            if sentence:
                yield sentence
            buf.clear()
            length = 0

    leftover = "".join(buf).strip()
    if leftover:
        yield leftover


def _parse_sse_tokens(response: requests.Response) -> Generator[str, None, None]:
    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue
        if line.startswith("data: "):
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                payload = json.loads(data_str)
                token = payload.get("token", "")
                if token:
                    yield token
            except json.JSONDecodeError:
                continue


class Orchestrator:

    def __init__(
        self,
        asr_url: str = "http://127.0.0.1:8000",
        llm_url: str = "http://127.0.0.1:8020",
        tts_url: str = "http://127.0.0.1:8030",
    ) -> None:
        self.asr_url = asr_url
        self.llm_url = llm_url
        self.tts_url = tts_url
        self._memory = ShortTermMemory()
        self._summarizer = Summarizer()
        self._tts_executor = ThreadPoolExecutor(max_workers=2)

    # ==================================================================
    # Legacy synchronous API (unchanged)
    # ==================================================================

    def transcribe(self, audio_path: str, language: str | None = None) -> tuple[str, str | None]:
        r = requests.post(
            f"{self.asr_url}/v1/asr/transcribe",
            json={"audio_path": audio_path, "language": language},
            timeout=120,
        )
        r.raise_for_status()
        body = r.json()
        return body["result"]["text"].strip(), body["result"].get("language")

    def chat(self, text: str, context: list[dict]) -> dict:
        r = requests.post(
            f"{self.llm_url}/v1/llm/chat",
            json={
                "event": {
                    "event_id": str(uuid.uuid4()),
                    "created_at": utc_now(),
                    "transcript": text,
                    "language": None,
                    "metadata": {},
                },
                "recent_memory": context,
            },
            timeout=120,
        )
        r.raise_for_status()
        return r.json()

    def speak(self, text: str, engine: str | None = None) -> None:
        payload = {"text": text}
        if engine:
            payload["engine"] = engine
        requests.post(f"{self.tts_url}/v1/tts/speak", json=payload, timeout=180)

    def load_context(self, limit: int = 8, max_age_minutes: float | None = 30.0) -> list[dict]:
        full = self._memory.load(limit=0, max_age_minutes=max_age_minutes)
        return self._summarizer.compress(full, keep_recent=limit)

    def save_memory(self, text: str, reply: dict) -> None:
        self._memory.append(text, reply)

    def run_turn(self, audio_path: str, language: str | None = None) -> dict:
        text, _lang = self.transcribe(audio_path, language)
        if not text:
            return {"ok": False, "error": "ASR returned empty text", "user_text": ""}
        ctx = self.load_context()
        reply = self.chat(text, ctx)
        reply_text = reply.get("reply_text", "").strip()
        self.speak(reply_text)
        self.save_memory(text, reply)
        return {"ok": True, "user_text": text, "reply_text": reply_text, "reply": reply}

    # ==================================================================
    # Low‑latency streaming API
    # ==================================================================

    def _stream_llm(self, user_text: str, context: list[dict]) -> Generator[str, None, None]:
        payload = {
            "event": {
                "event_id": str(uuid.uuid4()),
                "created_at": utc_now(),
                "transcript": user_text,
                "language": None,
                "metadata": {},
            },
            "recent_memory": context,
        }
        r = requests.post(
            f"{self.llm_url}/v1/llm/chat/stream",
            json=payload,
            stream=True,
            timeout=120,
        )
        r.raise_for_status()
        yield from _parse_sse_tokens(r)

    def _synthesize(self, text: str) -> bytes:
        gsvi_url = os.environ.get("GSVI_URL", "http://127.0.0.1:8050").rstrip("/")
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
        r = requests.post(
            f"{gsvi_url}/v1/audio/speech",
            json=payload,
            timeout=120,
        )
        r.raise_for_status()
        return r.content

    def run_turn_streaming_from_text(
        self, text: str, player: AsyncAudioPlayer
    ) -> dict:
        """Skip ASR — text already transcribed (e.g. from pseudo-streaming ASR)."""
        text = text.strip()
        if not text:
            return {"ok": False, "error": "Empty text", "user_text": ""}
        ctx = self.load_context()
        return self._finish_streaming(text, ctx, player)

    def run_turn_streaming(
        self,
        audio_path: str,
        player: AsyncAudioPlayer,
        language: str | None = None,
    ) -> dict:
        text, _lang = self.transcribe(audio_path, language)
        if not text:
            return {"ok": False, "error": "ASR returned empty text", "user_text": ""}

        ctx = self.load_context()
        return self._finish_streaming(text, ctx, player)
    def _finish_streaming(
        self, user_text: str, ctx: list[dict], player: AsyncAudioPlayer
    ) -> dict:
        """Shared streaming logic: LLM → sentence buffer → parallel TTS → player.

        TTS tasks are submitted to a thread pool as sentences become available,
        then resolved in order to guarantee correct playback sequence.
        """
        reply_full: list[str] = []
        tts_futures: list[tuple[str, Any]] = []  # (sentence, Future[bytes])
        first = True

        # Phase 1: stream LLM, submit TTS in parallel
        tokens = self._stream_llm(user_text, ctx)
        for sentence in _split_sentences(tokens, min_length=5, max_length=50):
            reply_full.append(sentence)

            if first:
                player.stop()
                player.resume()
                first = False

            future = self._tts_executor.submit(self._synthesize, sentence)
            tts_futures.append((sentence, future))

        if not reply_full:
            return {"ok": False, "error": "LLM returned empty", "user_text": user_text}

        # Phase 2: resolve futures in order, enqueue audio
        sentence_count = 0
        for sentence, future in tts_futures:
            sentence_count += 1
            try:
                wav = future.result()
                player.enqueue(wav)
            except Exception as exc:
                print(f"[Orchestrator] TTS error for sentence: {exc}")

        reply_text = "".join(reply_full).strip()

        reply_dict = {
            "reply_text": reply_text,
            "intent": "unknown",
            "actions": [],
            "memory": {},
            "raw": {},
        }
        self.save_memory(user_text, reply_dict)

        return {
            "ok": True,
            "user_text": user_text,
            "reply_text": reply_text,
            "reply": reply_dict,
            "sentence_count": sentence_count,
        }

