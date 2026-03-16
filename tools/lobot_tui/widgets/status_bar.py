"""StatusBar: bottom status line with timestamps and live indicator."""

from datetime import datetime, timedelta
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label
from textual.reactive import reactive

from ..data.collector import ClusterStateUpdated
from ..data.models import ClusterState


def _fmt_time(dt: "datetime | None") -> str:
    if dt is None:
        return "[dim]–[/]"
    return dt.strftime("%H:%M:%S")


def _is_stale(dt: "datetime | None", threshold_s: int = 30) -> bool:
    if dt is None:
        return True
    return (datetime.now() - dt).total_seconds() > threshold_s


class StatusBarWidget(Widget):
    """One-line status bar at the bottom of the main screen."""

    DEFAULT_CSS = """
    StatusBarWidget {
        height: 1;
        background: #161b22;
        layout: horizontal;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("", id="status-live")
        yield Label("", id="status-timestamps")
        yield Label(
            " [dim][q]quit [r]refresh [?]help [Tab]focus[/]",
            id="status-hint",
            markup=True,
        )

    def on_cluster_state_updated(self, event: ClusterStateUpdated) -> None:
        state = event.state
        live_label = self.query_one("#status-live", Label)
        ts_label = self.query_one("#status-timestamps", Label)

        # Live / stale / error indicator
        has_error = bool(state.pods_error or state.nodes_error)
        pods_stale = _is_stale(state.last_pods_update)

        if has_error:
            err = state.pods_error or state.nodes_error
            live_label.update(f"[red]✗ {err[:40]}[/]  ")
        elif pods_stale:
            live_label.update("[yellow]⚠ Stale[/]  ")
        else:
            live_label.update("[green]● Live[/]  ")

        pods_ts = _fmt_time(state.last_pods_update)
        nodes_ts = _fmt_time(state.last_nodes_update)
        ts_label.update(
            f"[dim]Pods:{pods_ts}  Nodes:{nodes_ts}[/]"
        )
