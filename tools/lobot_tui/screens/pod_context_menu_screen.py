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
        background: #161b22;
        border: solid #58a6ff;
        padding: 1 2;
    }
    #context-title {
        text-style: bold;
        color: #58a6ff;
        margin-bottom: 1;
        width: 1fr;
    }
    .ctx-btn {
        width: 1fr;
        height: 1;
        background: #1c2128;
        border: none;
        color: #c9d1d9;
        margin-bottom: 0;
    }
    .ctx-btn:hover {
        background: #1f6feb;
        color: #ffffff;
    }
    .ctx-btn:focus {
        background: #2d333b;
        border: none;
    }
    #ctx-delete {
        color: #f85149;
    }
    #ctx-delete:hover {
        background: #da3633;
        color: #ffffff;
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
