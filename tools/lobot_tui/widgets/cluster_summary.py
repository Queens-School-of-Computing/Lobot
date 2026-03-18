"""ResourceTableWidget: DataTable showing resource group utilisation."""

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import DataTable

from ..data.collector import ClusterStateUpdated
from ..data.models import ResourceSummary
from .render_utils import render_bar, render_gpu_bar, fmt_cpu, fmt_ram_gb, fmt_gpu

# Fixed-width columns (excluding RESOURCE which expands)
# CPU/RAM: bar_w=7 + " " + val=7 = 15.  GPU: bar_w=23 + " " + val=5 = 29.
_FIXED_COLS = [
    ("#",    3),
    ("CPU", 18),
    ("RAM", 18),
    ("GPU", 29),
]
_NUM_COLS = len(_FIXED_COLS) + 1
_FIXED_SUM = sum(w for _, w in _FIXED_COLS)
_RESOURCE_MIN = 10

# Sort key functions indexed by column (0=RESOURCE, then _FIXED_COLS order)
_SORT_KEYS = [
    lambda r: r.name,
    lambda r: r.pod_count,
    lambda r: r.cpu_used / r.cpu_total if r.cpu_total > 0 else 0,
    lambda r: r.ram_used_gb / r.ram_total_gb if r.ram_total_gb > 0 else 0,
    lambda r: r.gpu_used / r.gpu_total if r.gpu_total > 0 else 0,
]


class ResourceTableWidget(Widget):
    """Resource group utilisation table with row selection and filter support."""

    class ResourceFilterChanged(Message):
        """Posted when the user toggles a resource filter (via `r` hotkey)."""
        def __init__(self, resource_name: "str | None") -> None:
            super().__init__()
            self.resource_name = resource_name  # None = filter cleared

    _all_resources: dict = {}       # resource_name -> ResourceSummary
    _sorted_resources: list = []    # ordered list for cursor mapping
    _filter_resource: "str | None" = None
    _sort_col: int = -1
    _sort_rev: bool = False

    def compose(self) -> ComposeResult:
        yield DataTable(id="resource-datatable", cursor_type="row", zebra_stripes=True, cursor_foreground_priority="renderable")

    def on_mount(self) -> None:
        self._setup_columns()

    def on_resize(self) -> None:
        self._setup_columns()
        self._rebuild_table()

    def _resource_name_width(self) -> int:
        overhead = _FIXED_SUM + _NUM_COLS * 2 + 4
        return max(_RESOURCE_MIN, self.size.width - overhead)

    def _setup_columns(self) -> None:
        table = self.query_one(DataTable)
        table.clear(columns=True)
        table.add_column("RESOURCE", width=self._resource_name_width())
        for col_name, col_width in _FIXED_COLS:
            table.add_column(col_name, width=col_width)

    def on_cluster_state_updated(self, event: ClusterStateUpdated) -> None:
        if not event.state.resources and event.state.nodes_error:
            # Can't show table — leave columns but clear rows
            self.query_one(DataTable).clear()
            return
        self._all_resources = event.state.resources
        self._rebuild_table()

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
        self._rebuild_table()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Auto-update pod filter when navigating with filter active."""
        if self._filter_resource is None:
            return
        try:
            if not self.query_one(DataTable).has_focus:
                return
        except Exception:
            return
        res = self.selected_resource
        if res and res.name != self._filter_resource:
            self._filter_resource = res.name
            self.post_message(self.ResourceFilterChanged(res.name))
            self._rebuild_table()

    def toggle_filter(self) -> None:
        """Toggle pod filter on/off for currently selected resource (called by `r` hotkey)."""
        res = self.selected_resource
        if res is None:
            return
        if self._filter_resource is not None:
            self._filter_resource = None
            self.post_message(self.ResourceFilterChanged(None))
        else:
            self._filter_resource = res.name
            self.post_message(self.ResourceFilterChanged(res.name))
        self._rebuild_table()

    def clear_filter(self) -> None:
        """Clear the resource filter (called externally)."""
        if self._filter_resource is not None:
            self._filter_resource = None
            self.post_message(self.ResourceFilterChanged(None))
            self._rebuild_table()

    def _rebuild_table(self) -> None:
        table = self.query_one(DataTable)
        try:
            cursor_row = table.cursor_row
        except Exception:
            cursor_row = 0

        table.clear()

        if self._sort_col >= 0:
            sorted_resources = sorted(
                self._all_resources.values(),
                key=_SORT_KEYS[self._sort_col],
                reverse=self._sort_rev,
            )
        else:
            sorted_resources = sorted(
                self._all_resources.values(),
                key=lambda r: (0 if r.name.startswith("lobot_") else 1, r.name),
            )
        self._sorted_resources = sorted_resources

        for res in sorted_resources:
            pods_str = str(res.pod_count)

            cpu_str = render_bar(res.cpu_used, res.cpu_total, 10, fmt_cpu(res.cpu_used, res.cpu_total))
            ram_str = render_bar(res.ram_used_gb, res.ram_total_gb, 10, fmt_ram_gb(res.ram_used_gb, res.ram_total_gb))
            gpu_str = render_gpu_bar(res.gpu_used, res.gpu_total, fmt_gpu(res.gpu_used, res.gpu_total)) \
                      if res.has_gpu else f"[dim]{'–':>29}[/]"

            name_display = res.name
            if self._filter_resource and res.name == self._filter_resource:
                name_display = f"[bold cyan]{res.name}[/]"

            table.add_row(
                name_display,
                pods_str,
                cpu_str,
                ram_str,
                gpu_str,
                key=res.name,
            )

        if sorted_resources:
            row = min(cursor_row, len(sorted_resources) - 1)
            try:
                table.move_cursor(row=row)
            except Exception:
                pass

    @property
    def selected_resource(self) -> "ResourceSummary | None":
        if not self._sorted_resources:
            return None
        try:
            row = self.query_one(DataTable).cursor_row
            if 0 <= row < len(self._sorted_resources):
                return self._sorted_resources[row]
        except Exception:
            pass
        return None
