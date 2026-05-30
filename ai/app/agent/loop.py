"""Main agent loop — ties input state machine to the orchestrator."""

from app.agent.orchestrator import Orchestrator
from app.core.state import InputState
from app.input import InputManager


class AgentLoop:
    """Continuous voice agent: listen → process → speak → repeat."""

    def __init__(self, orchestrator: Orchestrator | None = None) -> None:
        self.orchestrator = orchestrator or Orchestrator()
        self.input = InputManager(silence_timeout=1.5, max_duration=30.0)
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
                print(f"[{turn}] Listening...")

                event = self.input.poll()
                if event["type"] == "stop":
                    break

                if event["type"] != "speech":
                    silent_turns += 1
                    if silent_turns >= 10:
                        print("Auto-exiting after 10 silent rounds.")
                        break
                    continue

                silent_turns = 0
                result = self.orchestrator.run_turn(event["audio_path"])

                if result["ok"]:
                    print(f"    User: {result['user_text']}")
                    print(f"    Assistant: {result['reply_text']}")
                    error_turns = 0
                else:
                    error_turns += 1
                    print(f"[{turn}] Error: {result.get('error')}")
                    if error_turns >= 5:
                        print("Auto-exiting after 5 consecutive errors.")
                        break

                self.input.transition(InputState.IDLE)

        except KeyboardInterrupt:
            print(f"\nStopped after {turn} turn(s).")
        finally:
            self.input.stop()

    def stop(self) -> None:
        self._running = False
        self.input.stop()
