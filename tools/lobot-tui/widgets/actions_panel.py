"""ActionsPanel: hint bar showing available keyboard actions."""

from textual.widget import Widget
from textual.widgets import Label


PODS_HINTS = (
    "[bold cyan][l][/] logs  "
    "[bold cyan][x][/] exec  "
    "[bold cyan][d][/] delete  "
    "[bold cyan][R][/] restart  "
    "[bold cyan][D][/] describe  "
    "[bold cyan][/][/] filter  "
    "[bold cyan][n][/] namespace"
)

NODES_HINTS = (
    "[bold cyan][c][/] cordon  "
    "[bold cyan][u][/] uncordon  "
    "[bold cyan][w][/] drain"
)

TOOLS_HINTS = (
    "[bold yellow][1][/] image-pull  "
    "[bold yellow][2][/] image-cleanup  "
    "[bold yellow][3][/] apply-config  "
    "[bold yellow][4][/] sync-groups  "
    "[bold yellow][5][/] helm upgrade  "
    "[bold yellow][6][/] announcement"
)


class ActionsPanelWidget(Widget):
    """Two-line key-hint bar."""

    DEFAULT_CSS = """
    ActionsPanelWidget {
        height: 2;
        background: #161b22;
        border-top: solid #30363d;
        padding: 0 1;
        layout: vertical;
    }
    """

    def compose(self):
        yield Label(
            f"PODS: {PODS_HINTS}   NODES: {NODES_HINTS}",
            markup=True,
        )
        yield Label(TOOLS_HINTS, markup=True)
