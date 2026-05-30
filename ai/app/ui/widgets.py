"""Reusable TUI widgets."""

from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import Horizontal


class StateBadge(Static):
    """Colored badge showing agent state."""

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


class ServiceRow(Static):
    """Show one service status line."""

    def set_status(self, name: str, status: str) -> None:
        icon = {"READY": "[green]●[/]", "BUSY": "[yellow]◉[/]", "ERROR": "[red]✖[/]", "OFFLINE": "[dim]○[/]"}.get(status, "[dim]?[/]")
        self.update(f"{icon} {name}: {status}")
