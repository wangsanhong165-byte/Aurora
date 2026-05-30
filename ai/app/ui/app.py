"""Voice Agent v1 TUI — Textual-based observability panel."""

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Header

from app.core.event_bus import bus
from app.ui.panels import LogPanel, StatusPanel, TurnPanel


class VoiceAgentUI(App):
    """Terminal control panel for monitoring the voice agent."""

    CSS_PATH = "styles.tcss"
    TITLE = "Voice Agent v1"
    BINDINGS = [("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        self._status = StatusPanel()
        yield self._status
        self._turn = TurnPanel()
        yield self._turn
        self._log = LogPanel()
        yield self._log

    def on_mount(self) -> None:
        self._status.set_service("asr", "OFFLINE")
        self._status.set_service("llm", "OFFLINE")
        self._status.set_service("tts", "OFFLINE")
        self._status.set_service("memory", "OFFLINE")
        self.set_interval(0.1, self._poll_events)

    def _poll_events(self) -> None:
        for event_type, data in bus.drain():
            if event_type == "state_changed":
                self._status.set_state(str(data))
                self._log.add(f"[State] {data}")
            elif event_type == "service_status":
                self._status.set_service(data.get("name", ""), data.get("status", "OFFLINE"))
            elif event_type == "user_text":
                self._turn.set_user(str(data))
                self._log.add(f"[User] {data}")
            elif event_type == "assistant_reply":
                self._turn.set_assistant(str(data))
                self._log.add(f"[AI] {data}")
            elif event_type == "log":
                self._log.add(str(data))
