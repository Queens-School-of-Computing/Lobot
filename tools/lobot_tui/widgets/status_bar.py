"""StatusBar: bottom status line with timestamps and live indicator."""

from datetime import datetime

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label

from ..data.collector import ClusterStateUpdated
from ..themes import COLOR_CRIT, COLOR_OK, COLOR_WARN

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
        background: $chrome-bg;
        layout: horizontal;
        padding: 0 1;
    }
    """

    _spinner_idx: int = 0
    _live: bool = False
    _last_longhorn_update: "datetime | None" = None
    _last_pods_update: "datetime | None" = None
    _last_nodes_update: "datetime | None" = None

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
            self.query_one("#status-live", Label).update(
                f"[{COLOR_OK}]{spin} Live[/] [cyan]svc[/]  "
            )
        except Exception:
            pass

    def on_cluster_state_updated(self, event: ClusterStateUpdated) -> None:
        state = event.state
        live_label = self.query_one("#status-live", Label)

        if state.service_error:
            self._live = False
            live_label.update(f"[{COLOR_CRIT}]✗ {state.service_error}[/]  ")
            if "not running" in state.service_error:
                self.query_one("#status-timestamps", Label).update(
                    "[dim]→  sudo systemctl start lobot-collector[/]"
                )
            else:
                self.query_one("#status-timestamps", Label).update(
                    "[dim]→  sudo journalctl -u lobot-collector -n 20[/]"
                )
            return

        has_error = bool(state.pods_error or state.nodes_error)
        pods_stale = _is_stale(state.last_pods_update)

        if has_error:
            self._live = False
            err = state.pods_error or state.nodes_error
            live_label.update(f"[{COLOR_CRIT}]✗ {err[:60]}[/]  ")
        elif pods_stale:
            self._live = False
            live_label.update(f"[{COLOR_WARN}]⚠ Stale[/] [cyan]svc[/]  ")
        else:
            self._live = True
            spin = _SPINNER[self._spinner_idx]
            live_label.update(f"[{COLOR_OK}]{spin} Live[/] [cyan]svc[/]  ")

        self._last_pods_update = state.last_pods_update
        self._last_nodes_update = state.last_nodes_update
        self._last_longhorn_update = state.last_longhorn_update
        self._update_timestamps()

    def _update_timestamps(self) -> None:
        pods_ts = _fmt_time(self._last_pods_update)
        nodes_ts = _fmt_time(self._last_nodes_update)
        disk_ts = _fmt_time(self._last_longhorn_update)
        try:
            self.query_one("#status-timestamps", Label).update(
                f"[dim]Pods:{pods_ts}  Nodes:{nodes_ts}  Disk:{disk_ts}[/]"
            )
        except Exception:
            pass
