"""Pipeline orchestrator: ASR → Memory → LLM → TTS → Memory save."""

import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

from app.memory.short_term import ShortTermMemory
from app.memory.summarizer import Summarizer


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Orchestrator:
    """Runs one turn: transcribe → chat → speak → remember."""

    def __init__(self,
                 asr_url: str = "http://127.0.0.1:8000",
                 llm_url: str = "http://127.0.0.1:8020",
                 tts_url: str = "http://127.0.0.1:8030",
                 ) -> None:
        self.asr_url = asr_url
        self.llm_url = llm_url
        self.tts_url = tts_url
        self._memory = ShortTermMemory()
        self._summarizer = Summarizer()

    def transcribe(self, audio_path: str, language: str | None = None) -> tuple[str, str | None]:
        r = requests.post(f"{self.asr_url}/v1/asr/transcribe",
                          json={"audio_path": audio_path, "language": language}, timeout=120)
        r.raise_for_status()
        body = r.json()
        return body["result"]["text"].strip(), body["result"].get("language")

    def chat(self, text: str, context: list[dict]) -> dict:
        r = requests.post(f"{self.llm_url}/v1/llm/chat",
                          json={"event": {"event_id": str(uuid.uuid4()),
                                          "created_at": utc_now(),
                                          "transcript": text,
                                          "language": None,
                                          "metadata": {}},
                                "recent_memory": context},
                          timeout=120)
        r.raise_for_status()
        return r.json()

    def speak(self, text: str, engine: str | None = None) -> None:
        payload = {"text": text}
        if engine:
            payload["engine"] = engine
        requests.post(f"{self.tts_url}/v1/tts/speak", json=payload, timeout=180)

    def load_context(self, limit: int = 8) -> list[dict]:
        """Load recent conversation with auto-summarization for long histories."""
        full = self._memory.load(limit=0)  # all
        return self._summarizer.compress(full, keep_recent=limit)

    def save_memory(self, text: str, reply: dict) -> None:
        self._memory.append(text, reply)

    def run_turn(self, audio_path: str, language: str | None = None) -> dict:
        """Execute one full turn and return result dict."""
        text, _lang = self.transcribe(audio_path, language)
        if not text:
            return {"ok": False, "error": "ASR returned empty text", "user_text": ""}

        ctx = self.load_context()
        reply = self.chat(text, ctx)
        reply_text = reply.get("reply_text", "").strip()

        self.speak(reply_text)
        self.save_memory(text, reply)

        return {"ok": True, "user_text": text, "reply_text": reply_text, "reply": reply}
