"""Unified turn runtime.

Agent loops collect input. This module owns how a turn is processed, whether the
input came from text or voice. Supports both non-streaming (via ChatPipeline) and
streaming (via Brain.respond_stream) paths.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Generator

from app.core.event_bus import bus
from app.core.events import EventType
from app.core.state import InputState, state_store
from app.models import ASRAdapter, TTSAdapter, HTTPASRAdapter, HTTPTTSAdapter
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.pipeline import ChatPipeline
from app.tts.player import AsyncAudioPlayer


# Sentence splitting regex (for TTS text, not raw JSON tokens)
_STRONG_END = re.compile(r"[\u3002\uFF01\uFF1F\n]")
_WEAK_END = re.compile(r"[\uFF0C\u3001\uFF1A,:]")
_MIN_WEAK = 12


def _split_text(text: str, min_len: int = 5, max_len: int = 50) -> list[str]:
    """Split display text into sentences for TTS. Only use on clean text, not JSON."""
    if not text:
        return []
    sentences: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if _STRONG_END.match(ch) and len(buf) >= min_len:
            sentences.append(buf)
            buf = ""
        elif _WEAK_END.match(ch) and len(buf) >= _MIN_WEAK:
            sentences.append(buf)
            buf = ""
        elif len(buf) >= max_len:
            sentences.append(buf)
            buf = ""
    if buf.strip():
        sentences.append(buf)
    return sentences


@dataclass(slots=True)
class TurnResult:
    ok: bool
    input_mode: str
    user_text: str = ""
    reply_text: str = ""
    error: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "input_mode": self.input_mode, "user_text": self.user_text, "reply_text": self.reply_text, "error": self.error, "raw": self.raw}


class TurnRuntime:
    """Single entry point for text and voice turns."""

    def __init__(
        self,
        runtime: AgentRuntime,
        llm_client: Any = None,
        model: str = "",
        llm_adapter: Any = None,
        player: AsyncAudioPlayer | None = None,
        asr_adapter: ASRAdapter | None = None,
        tts_adapter: TTSAdapter | None = None,
    ) -> None:
        self.pipeline = ChatPipeline(runtime, llm_client=llm_client, model=model, llm_adapter=llm_adapter)
        self.llm_adapter = llm_adapter
        self.asr = asr_adapter or HTTPASRAdapter()
        self.tts = tts_adapter or HTTPTTSAdapter()
        self.player = player or AsyncAudioPlayer()
        self._tts_executor = ThreadPoolExecutor(max_workers=2)

        self.disable_local_player: bool = False
        self.on_segment: Callable[[str, str, str], None] | None = None
        self.on_complete: Callable[[list, dict], None] | None = None
        self.on_tts_wav: Callable[[bytes, str], None] | None = None

        self.pipeline.on_segment = self._on_segment
        self.pipeline.on_complete = self._on_complete

    def start(self) -> None:
        self.player.start()

    def shutdown(self) -> None:
        self.player.shutdown(wait=False)

    # ---- input entry points ----------------------------------------------
    def process_text(self, text: str, screen_context: str = "") -> TurnResult:
        """Text input - shares the same streaming pipeline as voice."""
        state_store.update(input_state=InputState.PROCESSING.name)
        bus.publish(EventType.VOICE_INPUT, {"text": text, "mode": "text"}, source="turn_runtime")
        if self.llm_adapter:
            return self._process_streaming(text, mode="text")
        result = self.pipeline.process(text, screen_context=screen_context)
        reply = str(result.get("final_reply", ""))
        self._synthesize_tts_from_segments(result.get("segments", []))
        return TurnResult(ok=True, input_mode="text", user_text=text, reply_text=reply, raw=result)

    def process_audio(self, audio_path: str, language: str | None = None) -> TurnResult:
        """Process voice input."""
        state_store.update(input_state=InputState.PROCESSING.name)
        bus.publish(EventType.VOICE_INPUT, {"audio_path": audio_path, "language": language}, source="turn_runtime")
        try:
            asr_result = self.asr.transcribe(audio_path, language=language)
        except Exception as exc:
            state_store.update(input_state=InputState.IDLE.name)
            return TurnResult(ok=False, input_mode="voice", error=f"ASR failed: {exc}")

        text = str(asr_result.get("text", "")).strip()
        if not text:
            state_store.update(input_state=InputState.IDLE.name)
            return TurnResult(ok=False, input_mode="voice", error="ASR returned empty text")

        bus.publish(EventType.ASR_FINISHED, {"text": text, "audio_path": audio_path, "language": asr_result.get("language")}, source="turn_runtime")

        if self.llm_adapter:
            return self._process_streaming(text, mode="voice")

        result = self.pipeline.process(text)
        reply = str(result.get("final_reply", ""))
        self._synthesize_tts_from_segments(result.get("segments", []))
        state_store.update(input_state=InputState.SPEAKING.name)
        return TurnResult(ok=True, input_mode="voice", user_text=text, reply_text=reply, raw=result)

    # ---- streaming (shared by text and voice) ---------------------------
    def _process_streaming(self, text: str, mode: str = "voice") -> TurnResult:
        """Streaming pipeline: LLM -> accumulate -> parse JSON -> extract text -> TTS.
        
        Accepts raw token stream from LLM (which includes JSON syntax),
        accumulates the full response, parses it, extracts display text,
        and only then splits into sentences for TTS synthesis.
        """
        import time
        from app.brain.service import Brain

        state_store.update(input_state=InputState.SPEAKING.name)

        brain = Brain(character=self.pipeline.brain.character, tools=self.pipeline.brain.tools, runtime=self.pipeline.runtime)
        brain.history = list(self.pipeline.history)

        # Accumulate raw token stream
        raw_chunks: list[str] = []
        try:
            gen = brain.respond_stream(llm_adapter=self.llm_adapter, user_text=text)
            for chunk in gen:
                if chunk:
                    raw_chunks.append(chunk)
        except Exception as exc:
            bus.publish(EventType.LOG, {"message": f"Streaming error: {exc}"}, source="turn_runtime")

        full_response = "".join(raw_chunks).strip()

        # Debug: log raw LLM response
        if len(full_response) < 10:
            print(f"[LLM-raw] EMPTY or near-empty, len={len(full_response)}")
        else:
            print(f"[LLM-raw] len={len(full_response)} first=120:{full_response[:120]}")

        # Parse JSON reply and extract display text
        reply_text, segments = self._extract_reply_text(full_response)

        # Display segments
        for seg in segments:
            tone = seg.get("tone", "neutral")
            zh = seg.get("zh", "")
            en = seg.get("en", "") or seg.get("ja", "")
            display = zh or en
            if display and self.on_segment:
                self.on_segment(tone, zh, en)
            bus.publish(EventType.ASSISTANT_SEGMENT, {"tone": tone, "zh": zh, "en": en}, source="turn_runtime")

        self._synthesize_tts_from_segments(segments)

        reply_dict = {"reply_text": reply_text, "intent": "unknown", "actions": [], "memory": {}, "raw": {}}
        from app.memory.store import memory_store
        memory_store.enqueue_turn(text, reply_dict)
        # Persist history back to pipeline for next turn continuity
        self.pipeline.history = brain.history[:]

        bus.publish(EventType.ASSISTANT_REPLY, {"text": reply_text}, source="turn_runtime")
        bus.publish(EventType.TURN_COMPLETED, {"reply": reply_text, "stats": {"streaming": True, "mode": mode, "segment_count": len(segments)}}, source="turn_runtime")

        return TurnResult(ok=True, input_mode=mode, user_text=text, reply_text=reply_text)

    # ---- reply extraction ------------------------------------------------
    @staticmethod
    def _extract_reply_text(raw_response: str) -> tuple[str, list[dict]]:
        """Parse LLM JSON response and extract display text + segments.
        
        Returns (display_text, segments_list).
        """
        segments: list[dict] = []
        display = raw_response

        # Try to parse as JSON 鈥?with multiple fallback strategies
        data = None
        try:
            data = json.loads(raw_response)
        except (json.JSONDecodeError, Exception):
            pass

        if data is None:
            # Fallback 1: extract JSON between { }
            start = raw_response.find("{")
            end = raw_response.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(raw_response[start:end])
                except (json.JSONDecodeError, Exception):
                    pass

        if data is None and "segments" in raw_response:
            # Fallback 2: LLM forgot outer braces 鈥?wrap and retry
            try:
                data = json.loads("{" + raw_response + "}")
            except (json.JSONDecodeError, Exception):
                pass

        if data is None:
            print(f"[TTS-extract] all parse strategies failed, raw (first 120): {raw_response[:120]}")
            return display, segments

        # Extract segments
        if isinstance(data, dict):
            segs = data.get("segments", [])
            if isinstance(segs, list):
                segments = segs
            # Prefer final_reply, fall back to concatenating segment text
            final = data.get("final_reply", "")
            if final and isinstance(final, str) and final.strip():
                display = final.strip()
            elif segments:
                # Concatenate zh or en from segments
                parts = []
                for s in segments:
                    if isinstance(s, dict):
                        parts.append(s.get("zh", "") or s.get("en", "") or s.get("ja", ""))
                display = "".join(parts).strip() or display

        # Debug: warn if display is still the raw JSON response
        if display == raw_response and raw_response.startswith("{"):
            print(f"[TTS-extract] WARNING display==raw_response, len={len(raw_response)}")
        else:
            print(f"[TTS-extract] OK display_len={len(display)} segments={len(segments)}")

        return display, segments

    # ---- playback --------------------------------------------------------
    def wait_output_done(self, timeout: float | None = None) -> bool:
        done = self.player.wait_done(timeout=timeout)
        if done:
            state_store.update(input_state=InputState.IDLE.name)
        return done

    def _on_segment(self, tone: str, zh: str, ja: str) -> None:
        if self.on_segment:
            self.on_segment(tone, zh, ja)

    def _on_complete(self, segments: list, stats: dict) -> None:
        if self.on_complete:
            self.on_complete(segments, stats)

    def _synthesize_tts_from_segments(self, segments: list[dict]) -> None:
        """Synthesize TTS from parsed LLM segments, enqueue to player, broadcast to Web UI.

        Shared by streaming and non-streaming paths. Extracts native-language text
        from segments, splits into sentences, synthesizes in thread pool,
        enqueues for playback, and broadcasts audio URLs to web UI.
        """
        if not segments:
            # If the non-streaming path produced no segments, skip
            return

        # Determine native language from character card
        try:
            char_card = self.pipeline.runtime.character.active
            native_lang = char_card.get("tts", {}).get("prompt_lang", "ja")
        except Exception:
            native_lang = "ja"

        # Collect native-language text from all segments
        native_parts: list[str] = []
        for seg in segments:
            native_text = seg.get(native_lang, "") or seg.get("en", "") or seg.get("ja", "")
            if native_text:
                native_parts.append(native_text)
        tts_text = " ".join(native_parts).strip()

        if not tts_text:
            print(f"[TTS-lang] no native text found, lang={native_lang}")
            return

        tts_sentences = _split_text(tts_text, min_len=5, max_len=50)
        print(f"[TTS-lang] native={native_lang}  tts_text_len={len(tts_text)}  sentences={len(tts_sentences)}")

        # Guard: if it appears to be raw JSON, skip
        if tts_sentences and tts_sentences[0].startswith("{"):
            print(f"[TTS-guard] SKIP: tts_text appears to be raw JSON, len={len(tts_text)}")
            return

        if not self.disable_local_player:
            self.player.begin_turn()
        tts_futures: list[tuple[str, Any]] = []
        for sentence in tts_sentences:
            sentence = sentence.strip()
            if sentence:
                future = self._tts_executor.submit(self.tts.synthesize, sentence)
                tts_futures.append((sentence, future))
                bus.publish(EventType.TTS_REQUESTED, {"text": sentence, "tone": "neutral"}, source="turn_runtime")

        for sentence, future in tts_futures:
            try:
                wav = future.result()
                if wav:
                    if not self.disable_local_player:
                        self.player.enqueue(wav, text=sentence)
                    bus.publish(EventType.TTS_READY, {"text": sentence, "bytes": len(wav)}, source="turn_runtime")
                    if self.on_tts_wav:
                        self.on_tts_wav(wav, sentence)
            except Exception as exc:
                print(f"[TTS-synth] FAIL: {exc}  |  text='{sentence[:80]}'")
                bus.publish(EventType.LOG, {"message": f"TTS failed: {exc}"}, source="turn_runtime")

        if not self.disable_local_player:
            self.player.end_turn()
