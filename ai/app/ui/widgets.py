"""Reusable TUI widgets."""

from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import Horizontal


class StateBadge(Static):
    """Colored badge showing agent input state."""

    STATES = {
        "IDLE":        "dim",
        "LISTENING":   "cyan",
        "RECORDING":   "green",
        "PROCESSING":  "yellow",
        "SPEAKING":    "magenta",
        "INTERRUPTED": "red",
        "ERROR":       "red",
    }

    def set_state(self, state: str) -> None:
        color = self.STATES.get(state, "white")
        self.update(f"[bold {color}]{state:^14}[/]")


class EmotionBadge(Static):
    """Colored badge for emotional state."""

    COLORS = {
        "happy": "green", "sad": "blue", "surprised": "yellow",
        "thinking": "dim", "tired": "dim", "energetic": "green",
        "focused": "cyan", "relaxed": "magenta", "neutral": "white",
    }

    def set_emotion(self, emotion: str) -> None:
        color = self.COLORS.get(emotion, "white")
        self.update(f"[{color}]{emotion}[/]")


class ServiceRow(Static):
    """Show one service status line."""

    def set_status(self, name: str, status: str) -> None:
        icon = {"READY": "[green]●[/]", "BUSY": "[yellow]◉[/]", "ERROR": "[red]✖[/]", "OFFLINE": "[dim]○[/]"}.get(status, "[dim]?[/]")
        self.update(f"{icon} {name}: {status}")
