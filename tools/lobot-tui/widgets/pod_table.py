"""PodTable: DataTable widget showing jhub pods."""

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable, Input, Label, Static
from textual.reactive import reactive

from ..data.collector import ClusterStateUpdated
from ..data.models import ClusterState, PodInfo

COLUMNS = [
    ("USERNAME", 20),
    ("LAB", 14),
    ("NODE", 14),
    ("IMAGE TAG", 14),
    ("CPU", 5),
    ("RAM", 6),
    ("GPU", 4),
    ("AGE", 8),
    ("STATUS", 10),
]

PHASE_MARKUP = {
    "Running": "[green]Running[/]",
    "Pending": "[yellow]Pending[/]",
    "Failed": "[red]Failed[/]",
    "Succeeded": "[dim]Done[/]",
}


class PodTableWidget(Widget):
    """Pod list with inline filter."""

    filter_text: reactive[str] = reactive("")
    _all_pods: list = []
    _current_pods: list = []

    def compose(self) -> ComposeResult:
        yield Static("", id="pod-count-label")
        yield DataTable(id="pod-datatable", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        for col_name, col_width in COLUMNS:
            table.add_column(col_name, width=col_width)

    def on_cluster_state_updated(self, event: ClusterStateUpdated) -> None:
        self._all_pods = event.state.pods
        self._apply_filter()

    def watch_filter_text(self, value: str) -> None:
        self._apply_filter()

    def _apply_filter(self) -> None:
        f = self.filter_text.lower()
        if f:
            self._current_pods = [
                p for p in self._all_pods
                if f in p.username.lower()
                or f in p.node.lower()
                or f in p.lab.lower()
                or f in p.image_tag.lower()
                or f in p.phase.lower()
            ]
        else:
            self._current_pods = list(self._all_pods)
        self._rebuild_table()

    def _rebuild_table(self) -> None:
        table = self.query_one(DataTable)
        # Remember cursor position
        try:
            cursor_row = table.cursor_row
        except Exception:
            cursor_row = 0

        table.clear()
        for pod in self._current_pods:
            phase_display = PHASE_MARKUP.get(pod.phase, pod.phase)
            table.add_row(
                pod.username,
                pod.lab or "–",
                pod.node or "–",
                pod.image_tag,
                str(pod.cpu_requested),
                f"{pod.ram_requested_gb}G",
                str(pod.gpu_requested),
                pod.age,
                phase_display,
                key=pod.name,
            )

        # Restore cursor
        if self._current_pods:
            row = min(cursor_row, len(self._current_pods) - 1)
            try:
                table.move_cursor(row=row)
            except Exception:
                pass

        # Update count label
        total = len(self._all_pods)
        shown = len(self._current_pods)
        count_label = self.query_one("#pod-count-label", Static)
        if self.filter_text:
            count_label.update(f"[dim]{shown}/{total} pods[/]")
        else:
            count_label.update(f"[dim]{total} pod{'s' if total != 1 else ''}[/]")

    @property
    def selected_pod(self) -> "PodInfo | None":
        """Return the currently highlighted PodInfo, or None."""
        table = self.query_one(DataTable)
        if not self._current_pods:
            return None
        try:
            row = table.cursor_row
            if 0 <= row < len(self._current_pods):
                return self._current_pods[row]
        except Exception:
            pass
        return None
