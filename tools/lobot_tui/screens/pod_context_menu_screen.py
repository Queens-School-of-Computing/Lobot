"""PodContextMenuScreen: right-click context menu for a pod."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Label

from ..data.models import PodInfo


class PodContextMenuScreen(Screen):
    """Modal context menu showing pod actions."""

    DEFAULT_CSS = """
    PodContextMenuScreen {
        align: center middle;
    }
    #context-menu {
        width: 44;
        height: auto;
        background: $surface;
        border: solid $primary;
        padding: 1 2;
    }
    #context-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
        width: 1fr;
    }
    .ctx-btn {
        width: 1fr;
        height: 1;
        background: $panel;
        border: none;
        color: $foreground;
        margin-bottom: 0;
    }
    .ctx-btn:hover {
        background: $primary;
        color: $background;
    }
    .ctx-btn:focus {
        background: $bg-hover;
        border: none;
    }
    #ctx-delete {
        color: $error;
    }
    #ctx-delete:hover {
        background: $error;
        color: $background;
    }
    """

    BINDINGS = [("escape", "dismiss(None)", "Close")]

    def __init__(self, pod: PodInfo) -> None:
        super().__init__()
        self._pod = pod

    def compose(self) -> ComposeResult:
        with Vertical(id="context-menu"):
            yield Label(self._pod.name, id="context-title")
            yield Button("(l)  Logs", id="ctx-logs", classes="ctx-btn")
            yield Button("(x)  Exec into pod", id="ctx-exec", classes="ctx-btn")
            yield Button("(d)  Describe", id="ctx-describe", classes="ctx-btn")
            yield Button("(R)  Restart", id="ctx-restart", classes="ctx-btn")
            yield Button("(X)  Delete", id="ctx-delete", classes="ctx-btn")

    def on_mount(self) -> None:
        # Start focus on first button so keyboard works immediately
        self.query_one("#ctx-logs", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id.replace("ctx-", ""))
