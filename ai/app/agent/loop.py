"""v2 Agent Loop: input collection around the unified turn runtime."""
from __future__ import annotations

import os
import time
from typing import Any

from app.character.registry import CharacterRegistry
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.turn import TurnRuntime
from app.tools.registry import ToolRegistry




# App → activity mapping for state auto-inference
_APP_ACTIVITY_MAP: dict[str, str] = {
    "code": "coding", "devenv": "coding", "cursor": "coding",
    "vscode": "coding", "pycharm": "coding", "idea64": "coding",
    "Code": "coding", "clion64": "coding", "rider64": "coding",
    "chrome": "browsing", "msedge": "browsing", "firefox": "browsing",
    "explorer": "file_browsing", "terminal": "coding",
    "wechat": "chatting", "qq": "chatting", "discord": "chatting",
    "spotify": "music", "wmplayer": "video",
    "notepad": "writing", "obsidian": "writing", "notion": "writing",
    "steam": "gaming", "league of legends": "gaming",
}


class AgentLoop:
    """Main loop: collects input and feeds unified turns to TurnRuntime."""

    def __init__(
        self,
        persona: str | None = None,
        text_mode: bool = False,
    ) -> None:
        self.character = CharacterRegistry()
        if persona:
            self.character.activate(persona)

        self.tools = ToolRegistry()
        self.runtime = AgentRuntime(character=self.character, tools=self.tools)
        self.turns: TurnRuntime | None = None

        self.text_mode = text_mode
        self._running = False
        self._last_interaction = time.time()
        self._llm_adapter: Any = None
        self._initiative: Any = None
        self._screen_watcher: Any = None
        self._screen_enabled = os.environ.get("SCREEN_ENABLED", "0") == "1"
        self._last_initiative_time: float = 0.0
        self._initiative_cooldown: float = 120.0  # seconds between proactive messages
        self._web_mode: bool = False

    # ---- start / stop ----------------------------------------------------
    def start(self) -> None:
        """Start the main loop and all background services."""
        from app.models import OpenAILLMAdapter
        from app.memory.store import memory_store
        from app.initiative import InitiativeChecker, initiative_queue
        from app.screen import ScreenWatcher

        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            print("[AgentLoop] DEEPSEEK_API_KEY not set!")
            return

        adapter = OpenAILLMAdapter()
        self._llm_adapter = adapter
        self.turns = TurnRuntime(self.runtime, llm_adapter=adapter)

        self.turns.on_segment = self._on_segment
        self.turns.on_tts = self._on_tts
        self.turns.on_complete = self._on_complete
        self.turns.on_tts_wav = self._on_tts_wav
        self.turns.start()

        # Web mode: disable local player (browser handles playback)
        if self._web_mode:
            self.turns.disable_local_player = True

        # --- Memory: rebuild index on startup ---
        memory_store.set_llm_adapter(adapter)
        print(f"[AgentLoop] Memory store ready ({memory_store.rebuild_index()} facts)")


        # --- Initiative checker ---
        idle_sec = float(os.environ.get("INITIATIVE_IDLE_SEC", "300"))
        check_sec = float(os.environ.get("INITIATIVE_CHECK_SEC", "15"))
        self._initiative = InitiativeChecker(interval=check_sec, idle_threshold=idle_sec)
        self._initiative.on_initiative = self._on_initiative
        self._initiative.start()
        print(f"[AgentLoop] Initiative checker started (idle={idle_sec}s)")

        # --- Screen watcher ---
        if self._screen_enabled:
            self._screen_watcher = ScreenWatcher(interval=5.0)
            def on_screen_change(old: dict, new: dict) -> None:
                app = new.get("app", "").lower()
                # Auto-infer activity from app
                activity = _APP_ACTIVITY_MAP.get(app, "idle")
                from app.core.state import state_store
                state_store.update(activity=activity, context=app)
                # Push to initiative queue
                initiative_queue.push(
                    "screen_change",
                    {"from_app": old.get("app", ""), "to_app": new.get("app", ""),
                     "from_title": old.get("title", ""), "to_title": new.get("title", ""),
                     "inferred_activity": activity},
                    priority=2,
                )
            self._screen_watcher.on_context_change = on_screen_change
            self._screen_watcher.start()

        self._running = True
        print(f"[AgentLoop] Started (character={self.character.active_id}, text_mode={self.text_mode}, model={adapter.model})")
        # Start initiative buffer expiry thread (cleans unanswered entries)
        from app.core.initiative_buffer import initiative_buffer
        initiative_buffer.start_expiry()

        try:
            if self._web_mode:
                from app.ui.web_ui import get_web_input_queue
                wq = get_web_input_queue()
                self._run_web_input_loop(wq)
            elif self.text_mode:
                self._run_text_loop()
            else:
                self._run_voice_loop()
        finally:
            if self._screen_watcher:
                self._screen_watcher.stop()
            self._initiative.stop()
            # Save session episode before stopping memory
            if self._llm_adapter:
                memory_store.summarize_session(self._llm_adapter)
            # Save project state (last active time, session count)
            try:
                from app.project.store import ProjectStore
                ps = ProjectStore()
                data = ps.load()
                data["current"]["last_session"] = time.strftime("%Y-%m-%d %H:%M")
                data["current"]["session_count"] = data["current"].get("session_count", 0) + 1
                data["current"]["character"] = self.character.active_id
                ps.save(data)
                print("[Project] Session state saved")
            except Exception:
                pass
            memory_store.stop(wait=False)
            if self.turns:
                self.turns.shutdown()

    def stop(self) -> None:
        self._running = False
        if self.turns:
            self.turns.shutdown()

    # ---- voice loop ------------------------------------------------------
    def _run_voice_loop(self) -> None:
        import time
        import sounddevice as sd
        import soundfile as sf
        from pathlib import Path
        from app.core.state import InputState, state_store
        from app.input import InputManager

        BASE = Path(__file__).resolve().parent.parent.parent
        BEEP_START = BASE / "recordings" / "beep_start.wav"
        BEEP_END = BASE / "recordings" / "beep_end.wav"

        def _play_beep(path: Path) -> None:
            try:
                data, sr_rate = sf.read(str(path), dtype="float32")
                if data.ndim == 1:
                    data = data.reshape(-1, 1)
                sd.play(data, sr_rate)
                sd.wait()
            except Exception:
                pass

        inp = InputManager(silence_timeout=1.0, max_duration=30.0)
        inp.start()

        POST_PLAY_PAUSE = 0.25
        POST_BEEP_PAUSE = 0.12

        print("\n" + "=" * 48)
        print(f"  Agent v2  |  {self.character.active_id}  |  listening now")
        print("  Speak to interact. Ctrl+C to stop.")
        print("=" * 48 + "\n")

        turn = 0
        silent_turns = 0
        error_turns = 0

        print("[Input] beep")
        _play_beep(BEEP_START)
        time.sleep(POST_BEEP_PAUSE)

        try:
            while self._running:
                turn += 1
                print(f"[{turn}] Listening...")
                state_store.update(input_state=InputState.LISTENING.name)

                event = inp.poll()
                if event["type"] == "stop":
                    break

                if event["type"] != "speech":
                    silent_turns += 1
                    if silent_turns >= 10:
                        print("Auto-exiting after 10 silent rounds.")
                        break
                    continue

                _play_beep(BEEP_END)
                silent_turns = 0
                error_turns = 0

                self._initiative.touch()
                self._last_interaction = time.time()

                if not self.turns:
                    print("[AgentLoop] turn runtime not ready")
                    continue

                result = self.turns.process_audio(event["audio_path"])

                if result.ok:
                    print(f"    User: {result.user_text}")
                    print(f"    Assistant: {result.reply_text}")
                else:
                    error_turns += 1
                    print(f"[{turn}] Error: {result.error}")
                    if error_turns >= 5:
                        print("Auto-exiting after 5 consecutive errors.")
                        break

                self.turns.wait_output_done(timeout=60.0)
                time.sleep(POST_PLAY_PAUSE)

                print("[Input] beep")
                _play_beep(BEEP_START)
                time.sleep(POST_BEEP_PAUSE)

        except KeyboardInterrupt:
            print(f"\nStopped after {turn} turn(s).")
        finally:
            inp.stop()

    def _run_text_loop(self) -> None:
        print("=" * 48)
        print(f"  Agent v2 (text mode)  |  {self.character.active_id}")
        print("  Type to chat. /quit to exit.")
        print("=" * 48)
        self._run_stdin_loop()

    def _run_stdin_loop(self) -> None:
        while self._running:
            try:
                user = input("\nYou: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not user:
                continue
            if user.lower() in {"/quit", "/exit", "/q"}:
                break
            self._process_user_text(user)

    def _run_web_input_loop(self, wq) -> None:
        import queue
        import traceback
        while self._running:
            try:
                msg = wq.get(timeout=0.5)
                text = str(msg.get("text", "")).strip()
                if text:
                    if text.lower() in {"/quit", "/exit", "/q"}:
                        break
                    self._process_user_text(text)
            except queue.Empty:
                continue
            except Exception:
                traceback.print_exc()
                print("[WebInput] error processing message, continuing loop")
                continue

    def _process_user_text(self, user: str) -> None:
        screen = self._capture_screen_if_enabled()
        self._last_interaction = time.time()
        if hasattr(self._initiative, "touch"):
            self._initiative.touch()
        if self.turns:
            result = self.turns.process_text(user, screen_context=screen)
            if result.reply_text:
                print(f"Assistant: {result.reply_text}")
        else:
            print("[AgentLoop] turn runtime not ready")

    def _on_tts_wav(self, wav: bytes, text: str) -> None:
        try:
            from app.ui.web_ui import save_tts_audio, broadcast
            path = save_tts_audio(wav, text)
            if path:
                broadcast("tts_audio", {"path": path, "text": text[:60]})
        except Exception:
            pass

    def _on_segment(self, tone: str, zh: str, ja: str) -> None:
        self.character.portrait_for(tone)
        en = ja or ""
        if en:
            print(f"  [{tone}] {en}")
        if zh:
            print(f"         {zh}")
        # SSE broadcast to Web UI
        try:
            from app.ui.web_ui import broadcast
            broadcast("segment", {"tone": tone, "en": en, "zh": zh, "portrait": f"/portrait/{tone}"})
        except Exception:
            pass

    def _on_tts(self, text: str, tone: str) -> None:
        return None

    def _on_complete(self, segments: list, stats: dict) -> None:
        print(f"  [done] {stats['segment_count']} segments, "
              f"{stats['tool_rounds']} tool rounds, "
              f"{stats['elapsed']:.1f}s")

    def _on_initiative(self, events: list) -> None:
        """Called by InitiativeChecker when agent should proactively speak."""
        from app.core.state import state_store
        from app.core.state import mood_tracker
        from app.core.intent import compute_candidates, decide_action, describe_candidate
        from app.brain.service import Brain
        from app.brain.prompt_builder import PromptBuilder

        if not self._llm_adapter:
            print("[Initiative] No LLM adapter, skipping")
            return

        # Cooldown check: prevent spamming from rapid screen_change events
        elapsed_since_last = time.time() - self._last_initiative_time
        if elapsed_since_last < self._initiative_cooldown and self._last_initiative_time > 0:
            return

        # Step 1: compute initiative candidates from live state
        idle_sec = self._initiative.idle_seconds() if hasattr(self._initiative, 'idle_seconds') else time.time() - self._last_interaction
        ctx = state_store.snapshot() if self._screen_enabled else {}
        ms = mood_tracker
        candidates = compute_candidates(idle_sec, ms.mood, activity=ctx.get("activity", ""), events=events)

        # Step 2: decide whether to speak
        candidate = decide_action(candidates)
        self._last_initiative_time = time.time()  # record even if silent
        if candidate is None:
            if candidates:
                print(f"[Initiative] {len(candidates)} candidate(s) below threshold, staying silent")
            else:
                print(f"[Initiative] No candidates (idle={idle_sec:.0f}s), staying silent")
            return

        print(f"[Initiative] {describe_candidate(candidate)}")

        # Step 3: build structured initiative prompt from intent
        initiative_prompt = PromptBuilder.build_initiative_prompt(
            candidate["type"], candidate["topic"],
            activity=ctx.get("activity", ""),
            app_name=ctx.get("context", ""),
        )

        brain = Brain(character=self.character, tools=self.tools, runtime=self.runtime)
        brain.history = self.turns.pipeline.history if self.turns else []

        try:
            result = brain.respond(llm_adapter=self._llm_adapter, user_text=initiative_prompt, temperature=0.4)
            segments = result.segments  # list of {"en":..., "zh":..., "tone":...}
            reply_cn = result.final_reply.strip()
            if not reply_cn and segments:
                reply_cn = "".join(s.get("zh", "") for s in segments).strip()
            if reply_cn:
                print(f"[Initiative] Assistant: {reply_cn}")
                # Display segments (same pipeline as normal conversation)
                for seg in segments:
                    tone = seg.get("tone", "neutral")
                    zh = seg.get("zh", "")
                    en = seg.get("en", "")
                    self._on_segment(tone, zh, en)
                # Build TTS text from native language segments
                tts_text = " ".join(s.get("en", "") or s.get("ja", "") for s in segments).strip()
                if not tts_text:
                    tts_text = reply_cn
                if self.turns:
                    self._speak_proactive(tts_text)
                # Track for closure
                from app.core.initiative_buffer import initiative_buffer
                topic = reply_cn[:80]
                initiative_buffer.push(topic, tts_text)
        except Exception as exc:
            print(f"[Initiative] Brain call failed: {exc}")

    def _speak_proactive(self, text: str) -> None:
        """Synthesize and play proactive speech."""
        if not self.turns:
            return
        try:
            wav = self.turns.tts.synthesize(text)
            if wav:
                self.turns.player.enqueue(wav, text=text)
                self.turns.player.wait_done(timeout=30.0)
                print(f"[Initiative] Spoke: {text[:50]}...")
        except Exception as exc:
            print(f"[Initiative] TTS failed: {exc}")

    # ---- screen ----------------------------------------------------------
    def _capture_screen_if_enabled(self) -> str:
        if not self._screen_enabled:
            return ""
        try:
            from app.tools.builtins.screen import screen_capture
            return screen_capture()
        except Exception:
            return ""
