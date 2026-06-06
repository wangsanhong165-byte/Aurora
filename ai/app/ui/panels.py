"""TUI panels: status, conversation turn, initiative, logs."""

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static

from app.ui.widgets import StateBadge, EmotionBadge, ServiceRow


class StatusPanel(Container):
    """Top panel: input state + emotion + activity + services + memory."""

    def compose(self) -> ComposeResult:
        self._state = StateBadge("IDLE", id="state-badge")
        self._emotion = EmotionBadge("neutral", id="emotion-badge")
        self._activity = Static("", id="activity-line")
        self._memory = Static("", id="memory-line")
        self._asr = ServiceRow("", id="svc-asr")
        self._llm = ServiceRow("", id="svc-llm")
        self._tts = ServiceRow("", id="svc-tts")
        self._mem = ServiceRow("", id="svc-mem")

        with Container(id="status-panel"):
            with Horizontal(id="top-row"):
                yield self._state
                yield Static(" ", classes="spacer")
                yield self._emotion
            yield self._activity
            yield self._memory
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

    def set_emotion(self, emotion: str) -> None:
        self._emotion.set_emotion(emotion)

    def set_activity(self, activity: str) -> None:
        self._activity.update(f"  Activity: [bold]{activity}[/]")

    def set_memory(self, cards: int, index_size: int) -> None:
        self._memory.update(f"  Memory: [dim]{cards} cards, index={index_size}[/]")

    def set_service(self, name: str, status: str) -> None:
        mapping = {"asr": self._asr, "llm": self._llm, "tts": self._tts, "memory": self._mem}
        if widget := mapping.get(name):
            widget.set_status(name.upper(), status)


class TurnPanel(Container):
    """Last conversation turn with emotion."""

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


class InitiativePanel(Container):
    """Shows last proactive trigger."""

    def compose(self) -> ComposeResult:
        self._info = Static("", id="init-info")
        with Container(id="initiative-panel"):
            yield Static("  Initiative", classes="panel-title")
            yield self._info

    def set_trigger(self, reasons: str, idle_sec: int = 0) -> None:
        if idle_sec > 0:
            self._info.update(f"  Idle: {idle_sec}s | Trigger: [yellow]{reasons}[/]")
        else:
            self._info.update(f"  [dim]waiting...[/]")


class LogPanel(Container):
    """Scrolling log panel, last 40 lines."""

    MAX_LINES = 40

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
