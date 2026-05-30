"""Main agent loop — ties input state machine to the orchestrator."""

import time

from app.agent.orchestrator import Orchestrator
from app.core.event_bus import bus
from app.core.state import InputState
from app.input import InputManager
from app.input.interrupt import InterruptDetector


class AgentLoop:
    """Continuous voice agent: listen → process → speak → repeat."""

    def __init__(self, orchestrator: Orchestrator | None = None) -> None:
        self.orchestrator = orchestrator or Orchestrator()
        self.input = InputManager(silence_timeout=1.5, max_duration=30.0)
        self._interrupt = InterruptDetector()
        self._running = False

    def run(self) -> None:
        self._running = True
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
                bus.emit("log", f"[{turn}] Processing...")
                result = self.orchestrator.run_turn(event["audio_path"])

                if result["ok"]:
                    bus.emit("user_text", result["user_text"])
                    bus.emit("assistant_reply", result["reply_text"])
                    print(f"    User: {result['user_text']}")
                    print(f"    Assistant: {result['reply_text']}")
                    error_turns = 0
                else:
                    error_turns += 1
                    bus.emit("log", f"[{turn}] Error: {result.get('error')}")
                    print(f"[{turn}] Error: {result.get('error')}")
                    if error_turns >= 5:
                        bus.emit("log", "Auto-exiting after 5 consecutive errors.")
                        break

                # Interrupt check
                self.input.transition(InputState.SPEAKING)
                self._emit_state(InputState.SPEAKING)
                self._interrupt.reset()

                for _ in range(20):
                    frame = self.input._read_frame(timeout=0.05)
                    if frame is not None:
                        self._interrupt.feed(frame)
                    else:
                        break

                if self._interrupt.interrupted:
                    bus.emit("log", "Interrupt detected")
                    self.input.transition(InputState.IDLE)
                    continue

                self.input.transition(InputState.IDLE)

        except KeyboardInterrupt:
            bus.emit("log", f"Stopped after {turn} turn(s).")
            print(f"\nStopped after {turn} turn(s).")
        finally:
            self.input.stop()

    def _emit_state(self, state: InputState) -> None:
        bus.emit("state_changed", state.name)

    def stop(self) -> None:
        self._running = False
        self.input.stop()
