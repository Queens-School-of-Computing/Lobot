"""PodTable: DataTable widget showing jhub pods."""

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable, Static
from textual.reactive import reactive

from ..data.collector import ClusterStateUpdated
from ..data.models import PodInfo

# Fixed-width columns (excluding USERNAME which expands)
_FIXED_COLS = [
    ("LAB",       14),
    ("NODE",      24),
    ("IMAGE TAG", 34),
    ("CPU",        5),
    ("RAM",        6),
    ("GPU",        4),
    ("AGE",        8),
    ("STATUS",    10),
]
_NUM_COLS = len(_FIXED_COLS) + 1  # including USERNAME
_FIXED_SUM = sum(w for _, w in _FIXED_COLS)
_USERNAME_MIN = 14
_USERNAME_MAX = 30

PHASE_MARKUP = {
    "Running":   "[green]Running[/]",
    "Pending":   "[yellow]Pending[/]",
    "Failed":    "[red]Failed[/]",
    "Succeeded": "[dim]Done[/]",
}

def _left_trunc(text: str, width: int) -> str:
    """Truncate from the left so the tail (date) is always visible."""
    if len(text) <= width:
        return text
    return "…" + text[-(width - 1):]


# Sort key functions indexed by column position (0=POD, then _FIXED_COLS order)
_SORT_KEYS = [
    lambda p: p.name,
    lambda p: p.lab or "",
    lambda p: p.node or "",
    lambda p: p.image_tag,
    lambda p: p.cpu_requested,
    lambda p: p.ram_requested_gb,
    lambda p: p.gpu_requested,
    lambda p: p.age,
    lambda p: p.phase,
]


class PodTableWidget(Widget):
    """Pod list with inline filter and column sort."""

    filter_text: reactive[str] = reactive("")
    _all_pods: list = []
    _current_pods: list = []
    _sort_col: int = -1   # -1 = no sort
    _sort_rev: bool = False

    def compose(self) -> ComposeResult:
        yield DataTable(id="pod-datatable", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        self._setup_columns()

    def on_resize(self) -> None:
        self._setup_columns()
        self._rebuild_table()

    def _username_width(self) -> int:
        overhead = _FIXED_SUM + _NUM_COLS * 2 + 4
        return min(_USERNAME_MAX, max(_USERNAME_MIN, self.size.width - overhead))

    def _setup_columns(self) -> None:
        table = self.query_one(DataTable)
        table.clear(columns=True)
        table.add_column("POD", width=self._username_width())
        for col_name, col_width in _FIXED_COLS:
            table.add_column(col_name, width=col_width)

    def on_cluster_state_updated(self, event: ClusterStateUpdated) -> None:
        self._all_pods = event.state.pods
        self._apply_filter()

    def watch_filter_text(self, value: str) -> None:
        self._apply_filter()

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        """Toggle sort when a column header is clicked."""
        idx = event.column_index
        if idx >= len(_SORT_KEYS):
            return
        if self._sort_col == idx:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = idx
            self._sort_rev = False
        self._apply_filter()

    def _apply_filter(self) -> None:
        f = self.filter_text.strip().lower()
        if f:
            terms = [t.strip() for t in f.split("|") if t.strip()]
            def _matches(p: "PodInfo") -> bool:
                haystack = f"{p.name} {p.node} {p.lab} {p.image_tag} {p.phase}".lower()
                return any(t in haystack for t in terms)
            self._current_pods = [p for p in self._all_pods if _matches(p)]
        else:
            self._current_pods = list(self._all_pods)

        if self._sort_col >= 0:
            key_fn = _SORT_KEYS[self._sort_col]
            try:
                self._current_pods = sorted(
                    self._current_pods, key=key_fn, reverse=self._sort_rev
                )
            except Exception:
                pass

        self._rebuild_table()

    def _rebuild_table(self) -> None:
        table = self.query_one(DataTable)
        try:
            cursor_row = table.cursor_row
        except Exception:
            cursor_row = 0

        table.clear()
        for pod in self._current_pods:
            phase_display = PHASE_MARKUP.get(pod.phase, pod.phase)
            table.add_row(
                pod.name,
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

        if self._current_pods:
            row = min(cursor_row, len(self._current_pods) - 1)
            try:
                table.move_cursor(row=row)
            except Exception:
                pass

        total = len(self._all_pods)
        shown = len(self._current_pods)
        self.call_after_refresh(self._update_pod_count, total, shown)

    def _update_pod_count(self, total: int, shown: int) -> None:
        try:
            count_label = self.screen.query_one("#pod-count-outer", Static)
            if self.filter_text:
                count_label.update(f"{shown}/{total} pods")
            else:
                count_label.update(f"{total} pod{'s' if total != 1 else ''}")
        except Exception:
            pass

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
