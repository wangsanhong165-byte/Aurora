"""Unified turn runtime.

Agent loops collect input. This module owns how a turn is processed, whether the
input came from text or voice. Supports both non-streaming (via ChatPipeline) and
streaming (via Brain.respond_stream) paths.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.event_bus import bus
from app.core.events import EventType
from app.core.state import InputState, state_store
from app.models import ASRAdapter, TTSAdapter, HTTPASRAdapter, HTTPTTSAdapter
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.pipeline import ChatPipeline
from app.tts.player import AsyncAudioPlayer
from app.utils.sentence_splitter import split_sentences
from app.utils.tts_cleaner import tts_filter


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

        user_text = asr_result.get("text", "").strip()
        if not user_text:
            state_store.update(input_state=InputState.IDLE.name)
            return TurnResult(ok=False, input_mode="voice", error="No speech detected")

        if self.llm_adapter:
            return self._process_streaming(user_text, mode="voice")

        result = self.pipeline.process(user_text)
        reply = str(result.get("final_reply", ""))
        self._synthesize_tts_from_segments(result.get("segments", []))
        return TurnResult(ok=True, input_mode="voice", user_text=user_text, reply_text=reply, raw=result)

    # ---- streaming path --------------------------------------------------
    def _process_streaming(self, user_text: str, mode: str = "text") -> TurnResult:
        """Process a turn with streaming with on_segment/on_tts callbacks."""
        from app.brain.service import Brain
        brain = Brain(character=self.pipeline.runtime.character, tools=self.pipeline.runtime.tools, runtime=self.pipeline.runtime)
        brain.history = self.pipeline.history
        screen_context = ""
        system = self.pipeline.runtime.build_system(screen_context, user_query=user_text)
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        if brain.history:
            messages.extend(brain.history)
        messages.append({"role": "user", "content": user_text})

        stream_gen = self.llm_adapter.generate_stream(messages, temperature=0.3)
        collected: list[str] = []
        buffer = ""
        from app.utils.sentence_splitter import split_streaming

        for token in stream_gen:
            collected.append(token)
            buffer += token
            sentences, buffer = split_streaming(buffer, method="pysbd")
            for sentence in sentences:
                cleaned = tts_filter(sentence)
                if cleaned:
                    self._on_segment("neutral", cleaned, "")
                    if self._tts_and_play(cleaned):
                        if self.on_tts_wav:
                            pass
        # Flush leftover
        if buffer.strip():
            cleaned = tts_filter(buffer.strip())
            if cleaned:
                self._on_segment("neutral", cleaned, "")

        final_reply = "".join(collected)
        brain._record_turn(user_text, final_reply)
        return TurnResult(ok=True, input_mode=mode, user_text=user_text, reply_text=final_reply)

    def _tts_and_play(self, text: str) -> bool:
        """Synthesize and enqueue one sentence. Returns True if successful."""
        try:
            wav = self.tts.synthesize(text)
            if wav:
                if not self.disable_local_player:
                    self.player.enqueue(wav, text=text)
                if self.on_tts_wav:
                    self.on_tts_wav(wav, text)
                return True
        except Exception as exc:
            print(f"[TTS] FAIL: {exc}  |  text='{text[:80]}'")
        return False

    # ---- LLM output parsing ----------------------------------------------
    @staticmethod
    def _extract_tts_text(data: dict | str) -> tuple[str, list[dict]]:
        """Extract (tts_text, segments) from LLM response.
        
        Handles both parsed dict and raw JSON string.
        Returns (cleaned_display_text, segments_list).
        """
        raw_response = ""
        segments: list[dict] = []
        display = ""

        if isinstance(data, str):
            raw_response = data
            data = _try_parse_json(data)
        elif isinstance(data, dict):
            raw_response = json.dumps(data, ensure_ascii=False)

        if isinstance(data, dict):
            segs = data.get("segments", [])
            if isinstance(segs, list):
                segments = segs
            final = data.get("final_reply", "")
            if final and isinstance(final, str) and final.strip():
                display = final.strip()
            elif segments:
                parts = []
                for s in segments:
                    if isinstance(s, dict):
                        parts.append(s.get("zh", "") or s.get("en", "") or s.get("ja", ""))
                display = "".join(parts).strip() or display

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
        
        Uses pysbd for sentence splitting and tts_filter for text cleaning.
        Sends sentences to TTS engine in thread pool, enqueues for playback,
        and notifies the bridge for Web UI.
        """
        if not segments:
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

        raw_text = " ".join(native_parts).strip()

        if not raw_text:
            print(f"[TTS-lang] no native text found, lang={native_lang}")
            return

        # Clean text for TTS
        cleaned = tts_filter(raw_text)
        if not cleaned:
            print(f"[TTS-clean] all text filtered away, skipping")
            return

        # Split into sentences using pysbd
        tts_sentences = split_sentences(cleaned, method="pysbd")
        print(f"[TTS] lang={native_lang}  raw_len={len(raw_text)}  cleaned_len={len(cleaned)}  sentences={len(tts_sentences)}")

        # Guard: skip if it looks like raw JSON
        if tts_sentences and tts_sentences[0].startswith("{"):
            print(f"[TTS-guard] SKIP: tts_text appears to be raw JSON, len={len(cleaned)}")
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


def _try_parse_json(content: str) -> dict | str:
    """Try to parse JSON from content, return dict on success or original string."""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    if "```json" in content:
        try:
            return json.loads(content.split("```json")[1].split("```")[0])
        except (json.JSONDecodeError, IndexError):
            pass
    if "{" in content and "}" in content:
        try:
            return json.loads(content[content.find("{"):content.rfind("}") + 1])
        except json.JSONDecodeError:
            pass
    return content
