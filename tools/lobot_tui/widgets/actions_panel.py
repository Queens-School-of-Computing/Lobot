"""ActionsPanel: hint bar showing available keyboard actions."""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Label

_ROW1_LEFT = [
    ("[bold dim]PODS[/]",                   "hint-prefix"),
    ("[bold cyan](l)[/] logs",              "hint-pod"),
    ("[bold cyan](x)[/] exec",              "hint-pod"),
    ("[bold cyan](d)[/] describe",          "hint-pod"),
    ("[bold cyan](X)[/] delete",            "hint-pod"),
    ("[bold cyan](/)[/] filter",            "hint-pod"),
    ("[bold cyan](n)[/] ns",                "hint-pod"),
]

_ROW1_RIGHT = [
    ("[bold dim]TOOLS[/]",                  "hint-prefix"),
    ("[bold yellow](1)[/] image-pull",      "hint-tool"),
    ("[bold yellow](2)[/] image-cleanup",   "hint-tool"),
    ("[bold yellow](3)[/] apply-config",    "hint-tool"),
]

_ROW2_LEFT = [
    ("[bold dim]NODES[/]",                  "hint-prefix"),
    ("[bold cyan](c)[/] cordon",            "hint-node"),
    ("[bold cyan](u)[/] uncordon",          "hint-node"),
    ("[bold cyan](w)[/] drain",             "hint-node"),
]

_ROW2_RIGHT = [
    ("[bold yellow](4)[/] sync-groups",     "hint-tool"),
    ("[bold yellow](5)[/] helm upgrade",    "hint-tool"),
    ("[bold yellow](6)[/] announce",        "hint-tool"),
    ("[bold yellow](`)[/] console",         "hint-tool"),
    ("[bold dim](?)[/] help",               "hint-global"),
    ("[bold dim](q)[/] quit",               "hint-global"),
]


class ActionsPanelWidget(Widget):
    """Two-line key-hint bar: pod/node on left, tools on right."""

    DEFAULT_CSS = """
    ActionsPanelWidget {
        height: 2;
        background: #161b22;
        border-top: solid #30363d;
        padding: 0 1;
        layout: vertical;
    }
    ActionsPanelWidget Horizontal {
        height: 1;
        background: #161b22;
    }
    .hint-prefix {
        width: auto;
        color: #8b949e;
        padding: 0 1 0 0;
    }
    .hint-spacer {
        width: 1fr;
    }
    .hint-pod, .hint-node, .hint-tool, .hint-global {
        width: auto;
        padding: 0 1 0 0;
        color: #c9d1d9;
    }
    .hint-pod:hover, .hint-node:hover, .hint-tool:hover {
        text-style: underline;
        color: #58a6ff;
    }
    .hint-global {
        color: #8b949e;
    }
    """

    def compose(self) -> ComposeResult:
        with Horizontal():
            for text, cls in _ROW1_LEFT:
                yield Label(text, classes=cls, markup=True)
            yield Label("", classes="hint-spacer")
            for text, cls in _ROW1_RIGHT:
                yield Label(text, classes=cls, markup=True)
        with Horizontal():
            for text, cls in _ROW2_LEFT:
                yield Label(text, classes=cls, markup=True)
            yield Label("", classes="hint-spacer")
            for text, cls in _ROW2_RIGHT:
                yield Label(text, classes=cls, markup=True)
