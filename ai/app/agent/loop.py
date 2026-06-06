"""v2 Agent Loop: input collection around the unified turn runtime."""
from __future__ import annotations

import os
import time
from typing import Any

from app.character.registry import CharacterRegistry
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.turn import TurnRuntime
from app.tools.registry import ToolRegistry


_PROACTIVE_PROMPT = """[系统提示]
你是用户的长期陪伴AI助手。现在你检测到用户已经闲置了一段时间，或者发生了一些值得关注的事件。

当前状态: {state_summary}
触发原因: {trigger_reasons}

请根据以上信息，决定是否主动和用户说话：
- 如果有重要的事情要说，请自然地说出来
- 如果没什么特别的事，简短打个招呼或关心一下
- 如果用户状态是"focused"或"sleeping"，保持安静，返回空字符串

直接回复你要说的话（纯文本，不需要JSON）。如果不说话，返回空。"""


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

    # ---- start / stop ----------------------------------------------------
    def start(self) -> None:
        """Start the main loop and all background services."""
        from app.models import OpenAILLMAdapter
        from app.memory.background import memory_worker
        from app.memory.vector_index import memory_index
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
        self.turns.start()

        # --- Memory: rebuild index on startup ---
        count = memory_worker.rebuild_index()
        print(f"[AgentLoop] Memory index rebuilt: {count} cards")

        memory_worker.set_llm_adapter(adapter)
        memory_worker.start()
        print(f"[AgentLoop] Memory worker started (LLM-powered)")

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

        try:
            if self.text_mode:
                self._run_text_loop()
            else:
                self._run_voice_loop()
        finally:
            if self._screen_watcher:
                self._screen_watcher.stop()
            self._initiative.stop()
            memory_worker.stop(wait=False)
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
        while self._running:
            try:
                user = input("\nYou: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not user:
                continue
            if user.lower() in {"/quit", "/exit", "/q"}:
                break
            screen = self._capture_screen_if_enabled()
            self._last_interaction = time.time()
            self._initiative.touch()
            if self.turns:
                result = self.turns.process_text(user, screen_context=screen)
                if result.reply_text:
                    print(f"Assistant: {result.reply_text}")
                    # TTS playback handled inside process_text (shared streaming pipeline)
            else:
                print("[AgentLoop] turn runtime not ready")

    def _on_segment(self, tone: str, zh: str, ja: str) -> None:
        self.character.portrait_for(tone)
        print(f"  [{tone}] {zh or ''}")

    def _on_tts(self, text: str, tone: str) -> None:
        return None

    def _on_complete(self, segments: list, stats: dict) -> None:
        print(f"  [done] {stats['segment_count']} segments, "
              f"{stats['tool_rounds']} tool rounds, "
              f"{stats['elapsed']:.1f}s")

    def _on_initiative(self, events: list) -> None:
        """Called by InitiativeChecker when agent should proactively speak."""
        from app.core.state import state_store
        from app.brain.service import Brain

        if not self._llm_adapter:
            print("[Initiative] No LLM adapter, skipping")
            return

        event_types = [e.type for e in events]
        reasons = ", ".join(event_types)
        state = state_store.snapshot()
        state_summary = f"activity={state['activity']}, attention={state['attention']}, emotion={state['emotion']}"

        prompt = _PROACTIVE_PROMPT.format(state_summary=state_summary, trigger_reasons=reasons)
        print(f"[Initiative] Triggered: {reasons} | state={state_summary}")

        brain = Brain(character=self.character, tools=self.tools, runtime=self.runtime)
        brain.history = self.turns.pipeline.history if self.turns else []

        try:
            result = brain.respond(llm_adapter=self._llm_adapter, user_text=prompt, temperature=0.4)
            reply = result.final_reply.strip()
            if reply:
                print(f"[Initiative] Assistant: {reply}")
                # Speak proactively (voice and text mode both)
                if self.turns:
                    self._speak_proactive(reply)
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
