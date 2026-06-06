"""Voice Agent v2 TUI  Textual-based observability panel.

Starts AgentLoop in a background thread, polls the event bus for real-time
display of state, emotion, memory, initiative, and conversation.
"""

from __future__ import annotations

import threading
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Header

from app.core.event_bus import bus
from app.core.events import EventType
from app.ui.panels import LogPanel, StatusPanel, TurnPanel, InitiativePanel


class VoiceAgentUI(App):
    """Terminal control panel with integrated AgentLoop."""

    CSS_PATH = "styles.tcss"
    TITLE = "Voice Agent v2"
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, persona: str | None = None, text_mode: bool = False) -> None:
        super().__init__()
        self._persona = persona
        self._text_mode = text_mode
        self._loop: Any = None
        self._loop_thread: threading.Thread | None = None
        self._idle_seconds = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        self._status = StatusPanel()
        yield self._status
        self._turn = TurnPanel()
        yield self._turn
        self._initiative = InitiativePanel()
        yield self._initiative
        self._log = LogPanel()
        yield self._log

    def on_mount(self) -> None:
        # Initial status
        self._status.set_state("STARTING")
        self._status.set_emotion("neutral")
        self._status.set_activity("starting")
        self._status.set_memory(0, 0)
        self._initiative.set_trigger("waiting...")

        # Start AgentLoop in background thread
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True, name="agent-loop")
        self._loop_thread.start()

        # Poll events every 100ms
        self.set_interval(0.1, self._poll_events)
        # Update idle counter every 5s
        self.set_interval(5.0, self._update_idle)

    def on_unmount(self) -> None:
        if self._loop:
            self._loop.stop()

    def _run_loop(self) -> None:
        """Run AgentLoop in background thread."""
        from app.agent.loop import AgentLoop
        self._loop = AgentLoop(persona=self._persona, text_mode=self._text_mode)
        try:
            self._log.add("[System] Agent starting...")
            self._loop.start()
        except Exception as exc:
            bus.publish(EventType.LOG, {"message": f"AgentLoop crashed: {exc}"}, source="ui")
        finally:
            self._log.add("[System] Agent stopped")

    # ---- event polling ---------------------------------------------------
    def _poll_events(self) -> None:
        for event_type, data in bus.drain():
            payload = data.get("payload", data) if isinstance(data, dict) else data
            if not isinstance(payload, dict):
                payload = {"value": payload}

            if event_type == EventType.SERVICE_STATUS:
                self._status.set_service(
                    payload.get("name", ""),
                    payload.get("status", "OFFLINE"),
                )
                self._log.add(f"[Service] {payload.get('name','?')} → {payload.get('status','?')}")

            elif event_type == EventType.STATE_CHANGED:
                if "input_state" in payload:
                    self._status.set_state(payload["input_state"])
                if "emotion" in payload:
                    self._status.set_emotion(payload["emotion"])
                if "activity" in payload:
                    self._status.set_activity(payload["activity"])
                if "initiative_events" in payload:
                    self._initiative.set_trigger(
                        f"{payload['initiative_events']} events",
                        idle_sec=self._idle_seconds,
                    )

            elif event_type == EventType.USER_MESSAGE:
                text = payload.get("text", "")
                self._turn.set_user(str(text)[:80])
                self._log.add(f"[User] {text}")

            elif event_type == EventType.ASR_FINISHED:
                text = payload.get("text", "")
                self._turn.set_user(str(text)[:80])
                self._log.add(f"[ASR] {text}")

            elif event_type == EventType.BRAIN_STARTED:
                self._status.set_state("PROCESSING")
                inp = payload.get("input", "")
                self._log.add(f"[Brain] ← {str(inp)[:60]}")

            elif event_type == EventType.BRAIN_FINISHED:
                self._status.set_state("SPEAKING")
                reply = payload.get("reply", "")
                self._turn.set_assistant(str(reply)[:80])
                self._log.add(f"[Brain] → {str(reply)[:60]}")

            elif event_type == EventType.ASSISTANT_SEGMENT:
                text = payload.get("zh") or payload.get("ja") or ""
                if text:
                    self._turn.set_assistant(str(text)[:80])

            elif event_type == EventType.ASSISTANT_REPLY:
                text = payload.get("text", "")
                if text:
                    self._turn.set_assistant(str(text)[:80])

            elif event_type == EventType.MEMORY_BACKGROUND_FINISHED:
                cards = payload.get("total", payload.get("cards", 0))
                self._status.set_memory(cards, 0)
                self._log.add(f"[Memory] Flushed: {payload.get('extracted',0)} new, {cards} total")

            elif event_type == EventType.MEMORY_BACKGROUND_QUEUED:
                self._log.add(f"[Memory] Queued: {payload.get('user_text','')[:40]}")

            elif event_type == EventType.TURN_COMPLETED:
                self._status.set_state("IDLE")
                stats = payload.get("stats", {})
                self._log.add(f"[Turn] Done: {stats.get('segment_count',0)} seg, {stats.get('tool_rounds',0)} tools")

            elif event_type == EventType.TTS_REQUESTED:
                text = payload.get("text", "")
                self._log.add(f"[TTS] → {str(text)[:50]}")

            elif event_type == EventType.TTS_READY:
                self._log.add(f"[TTS] Ready: {payload.get('bytes',0)} bytes")

            elif event_type == EventType.LOG:
                msg = payload.get("message", str(payload))
                self._log.add(f"  {msg}")

    def _update_idle(self) -> None:
        """Update idle counter display."""
        import time
        if self._loop and hasattr(self._loop, '_last_interaction'):
            self._idle_seconds = int(time.time() - self._loop._last_interaction)
