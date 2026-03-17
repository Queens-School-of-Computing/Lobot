"""StatusBar: bottom status line with timestamps and live indicator."""

from datetime import datetime
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label

from ..data.collector import ClusterStateUpdated

_SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


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

    _spinner_idx: int = 0
    _live: bool = False
    _last_source: str = "kubectl"

    def compose(self) -> ComposeResult:
        yield Label("", id="status-live")
        yield Label("", id="status-timestamps")
        yield Label(
            " [dim][q]quit [R]refresh [?]help [Tab]focus[/]",
            id="status-hint",
            markup=True,
        )

    def on_mount(self) -> None:
        self.set_interval(0.15, self._tick_spinner)

    def _tick_spinner(self) -> None:
        if not self._live:
            return
        self._spinner_idx = (self._spinner_idx + 1) % len(_SPINNER)
        try:
            spin = _SPINNER[self._spinner_idx]
            source_tag = "[cyan]svc[/]" if self._last_source == "service" else "[dim]kubectl[/]"
            self.query_one("#status-live", Label).update(
                f"[#3fb950]{spin} Live[/] {source_tag}  "
            )
        except Exception:
            pass

    def on_cluster_state_updated(self, event: ClusterStateUpdated) -> None:
        state = event.state
        live_label = self.query_one("#status-live", Label)
        ts_label = self.query_one("#status-timestamps", Label)

        has_error = bool(state.pods_error or state.nodes_error)
        pods_stale = _is_stale(state.last_pods_update)
        source_tag = "[cyan]svc[/]" if event.source == "service" else "[dim]kubectl[/]"
        self._last_source = event.source

        if has_error:
            self._live = False
            err = state.pods_error or state.nodes_error
            live_label.update(f"[#f85149]✗ {err[:40]}[/]  ")
        elif pods_stale:
            self._live = False
            live_label.update(f"[#d29922]⚠ Stale[/] {source_tag}  ")
        else:
            self._live = True
            spin = _SPINNER[self._spinner_idx]
            live_label.update(f"[#3fb950]{spin} Live[/] {source_tag}  ")

        pods_ts = _fmt_time(state.last_pods_update)
        nodes_ts = _fmt_time(state.last_nodes_update)
        ts_label.update(
            f"[dim]Pods:{pods_ts}  Nodes:{nodes_ts}[/]"
        )
