"""Main agent loop ? ties input state machine to the orchestrator.

Flow: listen ? process ? speak ? wait ? beep ? listen (no echo interrupt)
"""

import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from app.agent.orchestrator import Orchestrator
from app.core.event_bus import bus
from app.core.state import InputState
from app.input import InputManager
from app.tts.player import AsyncAudioPlayer


BEEP_START = Path(__file__).resolve().parent.parent.parent / "recordings" / "beep_start.wav"
BEEP_END = Path(__file__).resolve().parent.parent.parent / "recordings" / "beep_end.wav"


def _play_beep(path: Path) -> None:
    """Play a short beep from the given WAV file."""
    try:
        data, sr = sf.read(str(path), dtype="float32")
        if data.ndim == 1:
            data = data.reshape(-1, 1)
        sd.play(data, sr)
        sd.wait()
    except Exception:
        pass  # silent fail if audio device not available


class AgentLoop:
    """Continuous voice agent: beep ? listen ? process ? speak ? wait ? repeat.

    Playback and listening are fully serialized:
    - AI speaks ? wait for all audio to finish ? beep ? start listening.
    - No interrupt monitoring during playback (avoids echo false-positives).
    """

    def __init__(self, orchestrator: Orchestrator | None = None) -> None:
        self.orchestrator = orchestrator or Orchestrator()
        self.input = InputManager(silence_timeout=1.0, max_duration=30.0)
        self._player = AsyncAudioPlayer()
        self._running = False

    def run(self) -> None:
        self._running = True
        self._player.start()
        self.input.start()

        print("\n" + "=" * 48)
        print("  All services ready ? listening now")
        print("  Speak to interact. Ctrl+C to stop.")
        print("=" * 48 + "\n")

        turn = 0
        silent_turns = 0
        error_turns = 0

        # Play initial beep to signal readiness
        _play_beep(BEEP_START)

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

                # Confirm reception with end beep
                _play_beep(BEEP_END)
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

                # Wait for ALL TTS playback to finish (no interrupt monitoring)
                self._emit_state(InputState.SPEAKING)
                self._player.wait_done(timeout=60.0)
                # Small pause before beep to avoid overlap
                time.sleep(0.2)

                # Signal "ready to listen" with a beep
                _play_beep(BEEP_START)

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
