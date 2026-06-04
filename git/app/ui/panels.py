"""TUI panels: status, conversation turn, logs."""

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Static

from app.ui.widgets import StateBadge, ServiceRow


class StatusPanel(Container):
    """Top panel: agent state + service status."""

    def compose(self) -> ComposeResult:
        self._state = StateBadge("IDLE", id="state-badge")
        self._asr = ServiceRow("", id="svc-asr")
        self._llm = ServiceRow("", id="svc-llm")
        self._tts = ServiceRow("", id="svc-tts")
        self._mem = ServiceRow("", id="svc-mem")

        with Container(id="status-panel"):
            yield Static("  Agent State", classes="panel-title")
            yield self._state
            yield Static("  Services", classes="panel-title")
            yield self._asr
            yield self._llm
            yield self._tts
            yield self._mem

    def on_mount(self) -> None:
        self._asr.set_status("ASR", "OFFLINE")
        self._llm.set_status("LLM", "OFFLINE")
        self._tts.set_status("TTS", "OFFLINE")
        self._mem.set_status("Memory", "OFFLINE")

    def set_state(self, state: str) -> None:
        self._state.set_state(state)

    def set_service(self, name: str, status: str) -> None:
        mapping = {"asr": self._asr, "llm": self._llm, "tts": self._tts, "memory": self._mem}
        if widget := mapping.get(name):
            widget.set_status(name.upper(), status)


class TurnPanel(Container):
    """Last conversation turn."""

    def compose(self) -> ComposeResult:
        self._user = Static("", id="turn-user")
        self._ai = Static("", id="turn-ai")
        with Container(id="turn-panel"):
            yield Static("  Last Turn", classes="panel-title")
            yield self._user
            yield self._ai

    def set_user(self, text: str) -> None:
        self._user.update(f"  [bold yellow]User:[/] {text}")

    def set_assistant(self, text: str) -> None:
        self._ai.update(f"  [bold cyan]AI:[/]   {text}")


class LogPanel(Container):
    """Scrolling log panel, last 30 lines."""

    MAX_LINES = 30

    def compose(self) -> ComposeResult:
        self._log = Static("", id="log-lines")
        with Container(id="log-panel"):
            yield Static("  Logs", classes="panel-title")
            yield self._log

    def add(self, msg: str) -> None:
        if not hasattr(self, "_lines"):
            self._lines: list[str] = []
        self._lines.append(msg)
        if len(self._lines) > self.MAX_LINES:
            self._lines = self._lines[-self.MAX_LINES:]
        self._log.update("\n".join(self._lines))
