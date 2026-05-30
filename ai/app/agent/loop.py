"""Main agent loop — ties input state machine to the orchestrator."""

import time

from app.agent.orchestrator import Orchestrator
from app.core.event_bus import bus
from app.core.state import InputState
from app.input import InputManager
from app.input.interrupt import InterruptDetector
from app.tts.player import AsyncAudioPlayer


class AgentLoop:
    """Continuous voice agent: listen → process → speak → repeat.

    Uses streaming LLM + sentence-buffer TTS + async player for low latency.
    """

    def __init__(self, orchestrator: Orchestrator | None = None) -> None:
        self.orchestrator = orchestrator or Orchestrator()
        self.input = InputManager(silence_timeout=0.7, max_duration=30.0)
        self._interrupt = InterruptDetector()
        self._player = AsyncAudioPlayer()
        self._running = False

    def run(self) -> None:
        self._running = True
        self._player.start()
        self.input.start()

        print("\n" + "=" * 48)
        print("  All services ready — listening now")
        print("  Speak to interact. Ctrl+C to stop.")
        print("=" * 48 + "\n")

        turn = 0
        silent_turns = 0
        error_turns = 0

        try:
            while self._running:
                turn += 1
                self._emit_state(InputState.IDLE)
                print(f"[{turn}] Listening...")
                bus.emit("log", f"[{turn}] Listening...")

                event = self.input.poll()
                if event["type"] == "stop":
                    break

                if event["type"] != "speech":
                    silent_turns += 1
                    if silent_turns >= 10:
                        bus.emit("log", "Auto-exiting after 10 silent rounds.")
                        break
                    continue

                self._emit_state(InputState.PROCESSING)
                silent_turns = 0
                error_turns = 0
                bus.emit("log", f"[{turn}] Processing...")

                result = self.orchestrator.run_turn_streaming(
                    event["audio_path"], self._player
                )

                if result["ok"]:
                    bus.emit("user_text", result["user_text"])
                    bus.emit("assistant_reply", result["reply_text"])
                    print(f"    User: {result['user_text']}")
                    print(f"    Assistant: {result['reply_text']}")
                    sentence_count = result.get("sentence_count", 0)
                    bus.emit("log", f"[{turn}] Sent {sentence_count} sentence(s) to player")
                else:
                    error_turns += 1
                    bus.emit("log", f"[{turn}] Error: {result.get('error')}")
                    print(f"[{turn}] Error: {result.get('error')}")
                    if error_turns >= 5:
                        bus.emit("log", "Auto-exiting after 5 consecutive errors.")
                        break

                self.input.transition(InputState.SPEAKING)
                self._emit_state(InputState.SPEAKING)
                self._interrupt.reset()

                monitor_start = time.monotonic()
                while self._player.is_playing:
                    if time.monotonic() - monitor_start > 30.0:
                        break
                    frame = self.input._read_frame(timeout=0.05)
                    if frame is not None:
                        self._interrupt.feed(frame)
                    if self._interrupt.interrupted:
                        bus.emit("log", "Interrupt detected — stopping playback")
                        self._player.stop()
                        break

                self.input.transition(InputState.IDLE)

        except KeyboardInterrupt:
            bus.emit("log", f"Stopped after {turn} turn(s).")
            print(f"\nStopped after {turn} turn(s).")
        finally:
            self.input.stop()
            self._player.shutdown(wait=False)

    def _emit_state(self, state: InputState) -> None:
        bus.emit("state_changed", state.name)

    def stop(self) -> None:
        self._running = False
        self.input.stop()
        self._player.shutdown(wait=False)
