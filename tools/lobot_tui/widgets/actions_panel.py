"""ActionsPanel: hint bar showing available keyboard actions."""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Label

# (text, css_class, action_key)  — key=None for non-clickable prefixes
_ROW1_LEFT = [
    ("[bold dim]PODS[/]", "hint-prefix", None),
    ("[bold cyan](l)[/] logs", "hint-pod", "l"),
    ("[bold cyan](x)[/] exec", "hint-pod", "x"),
    ("[bold cyan](d)[/] describe", "hint-pod", "d"),
    ("[bold cyan](X)[/] delete", "hint-pod", "X"),
    ("[bold cyan](f)[/] filter", "hint-pod", "f"),
    ("[bold cyan](N)[/] ns", "hint-pod", "N"),
]

_ROW1_RIGHT = [
    ("[bold dim]TOOLS[/]", "hint-prefix", None),
    ("[bold yellow](1)[/] image-pull", "hint-tool", "1"),
    ("[bold yellow](2)[/] image-cleanup", "hint-tool", "2"),
    ("[bold yellow](3)[/] apply-config", "hint-tool", "3"),
    ("[bold yellow](4)[/] sync-groups", "hint-tool", "4"),
    ("[bold yellow](5)[/] helm upgrade", "hint-tool", "5"),
    ("[bold yellow](6)[/] announce", "hint-tool", "6"),
]

_ROW2_LEFT = [
    ("[bold dim]NODES[/]", "hint-prefix", None),
    ("[bold cyan](n)[/] node filter", "hint-node", "n"),
    ("[bold cyan](r)[/] resource filter", "hint-node", "r"),
    ("[bold cyan](c)[/] cordon", "hint-node", "c"),
    ("[bold cyan](u)[/] uncordon", "hint-node", "u"),
    ("[bold cyan](w)[/] drain", "hint-node", "w"),
]

_ROW2_RIGHT = [
    ("[bold yellow](`)[/] console", "hint-tool", "`"),
    ("[bold yellow](b)[/] jobs", "hint-tool", "b"),
    ("[bold yellow](?)[/] help", "hint-tool", "?"),
    ("[bold yellow](G)[/] guide", "hint-tool", "G"),
    ("[bold yellow](T)[/] theme", "hint-tool", "T"),
    ("[bold yellow](q)[/] quit", "hint-tool", "q"),
]


class HintClicked(Message):
    """Posted by HintLabel when clicked. Bubbles up to MainScreen."""

    def __init__(self, key: str) -> None:
        super().__init__()
        self.key = key


class HintLabel(Label):
    """A clickable key-hint label. Emits HintClicked on click."""

    def __init__(self, text: str, key: str | None, **kwargs) -> None:
        super().__init__(text, **kwargs)
        self._hint_key = key

    def on_click(self) -> None:
        if self._hint_key:
            self.post_message(HintClicked(self._hint_key))


class ActionsPanelWidget(Widget):
    """Two-line key-hint bar: pod/node on left, tools on right."""

    # Re-export so callers can still use ActionsPanelWidget.HintClicked
    HintClicked = HintClicked

    DEFAULT_CSS = """
    ActionsPanelWidget {
        height: 2;
        background: $chrome-bg;
        padding: 0 1;
        layout: vertical;
    }
    ActionsPanelWidget Horizontal {
        height: 1;
        background: $chrome-bg;
    }
    .hint-prefix {
        width: auto;
        color: $text-muted;
        padding: 0 1 0 0;
    }
    .hint-spacer {
        width: 1fr;
    }
    .hint-pod, .hint-node, .hint-tool, .hint-global {
        width: auto;
        padding: 0 1 0 0;
        color: $foreground;
    }
    .hint-pod:hover, .hint-node:hover, .hint-tool:hover {
        text-style: underline;
        color: $primary;
    }
    .hint-global {
        color: $text-muted;
    }
    #job-status-label {
        width: auto;
        display: none;
    }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(id="panel-row1"):
            for text, cls, key in _ROW1_LEFT:
                yield HintLabel(text, key, classes=cls, markup=True)
            yield Label("", classes="hint-spacer")
            # Row-1 right tool hints (hidden when a job is running)
            for text, cls, key in _ROW1_RIGHT:
                yield HintLabel(text, key, classes="hint-tools-right " + cls, markup=True)
        with Horizontal(id="panel-row2"):
            for text, cls, key in _ROW2_LEFT:
                yield HintLabel(text, key, classes=cls, markup=True)
            yield Label("", classes="hint-spacer")
            # Row-2 right hints (hidden when a job is running)
            for text, cls, key in _ROW2_RIGHT:
                yield HintLabel(text, key, classes="hint-tools-right " + cls, markup=True)
            # Job status label (shown when a job is running, replaces hints above)
            yield Label("", id="job-status-label", markup=True)

    def set_job_status(self, text: str | None) -> None:
        """Show job status in place of all right-side tool hints, or restore them if text is None."""
        job_label = self.query_one("#job-status-label", Label)
        right_hints = self.query(".hint-tools-right")
        if text is None:
            job_label.display = False
            for w in right_hints:
                w.display = True
        else:
            for w in right_hints:
                w.display = False
            job_label.update(text)
            job_label.display = True
