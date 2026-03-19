"""NodeTable: DataTable widget showing cluster nodes."""

from textual import events
from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import DataTable

from ..data.collector import ClusterStateUpdated
from ..data.models import NodeInfo
from .render_utils import (
    filter_highlight,
    fmt_cpu,
    fmt_gpu,
    fmt_ram_gb,
    plain_text,
    render_bar,
    render_bar_text,
    render_gpu_bar,
    render_gpu_bar_text,
    row_bg_for_node,
    status_badge,
    status_badge_text,
)

# Fixed-width columns (excluding NAME which expands)
_FIXED_COLS = [
    ("RESOURCE", 20),
    ("STATUS", 10),
    ("DISK", 18),
    ("CPU", 18),
    ("RAM", 18),
    ("GPU", 29),
]
_NUM_COLS = len(_FIXED_COLS) + 1  # including NAME
_FIXED_SUM = sum(w for _, w in _FIXED_COLS)
_NAME_MIN = 16


# Sort key functions indexed by column (0=NAME, then _FIXED_COLS order)
def _status_order(n: NodeInfo) -> int:
    if n.is_control_plane:
        return 0
    if n.status == "Ready" and n.schedulable:
        return 1
    if n.status == "Ready" and not n.schedulable:
        return 2
    if n.status == "NotReady":
        return 3
    return 4


_SORT_KEYS = [
    lambda n: n.name,
    lambda n: n.resource or "",
    _status_order,
    lambda n: n.cpu_requested,
    lambda n: n.ram_requested_gb,
    lambda n: n.gpu_requested,
    # DISK (col 6) has no sort key; header click is a no-op via idx >= len guard
]


class NodeTableWidget(Widget):
    """Node list with status and resource utilisation."""

    class NodeFilterChanged(Message):
        """Posted when the user toggles a node filter (Enter on a row)."""

        def __init__(self, node_name: "str | None") -> None:
            super().__init__()
            self.node_name = node_name  # None = filter cleared

    _all_nodes: list = []
    _sorted_nodes: list = []
    _sort_col: int = -1
    _sort_rev: bool = False
    _filter_node: "str | None" = None  # node name actively filtering pods
    _disk_data: dict = {}  # {node_name: [DiskInfo, ...]} from LonghornDataUpdated
    _expanded_nodes: set = set()  # node names whose disk sub-rows are visible
    _row_entries: list = []  # flat list of (NodeInfo, DiskInfo|None) per table row

    def compose(self) -> ComposeResult:
        yield DataTable(
            id="node-datatable",
            cursor_type="row",
            zebra_stripes=True,
            cursor_foreground_priority="renderable",
        )

    def on_mount(self) -> None:
        self._setup_columns()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Toggle disk expansion on mouse click (or Enter)."""
        self._toggle_expand()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Auto-update pod filter when navigating with filter active."""
        if self._filter_node is None:
            return
        try:
            if not self.query_one(DataTable).has_focus:
                return
        except Exception:
            return
        node = self.selected_node
        if node and node.name != self._filter_node:
            self._filter_node = node.name
            self.post_message(self.NodeFilterChanged(node.name))
            self._rebuild_table()

    def on_resize(self) -> None:
        self._setup_columns()
        self._rebuild_table()

    def on_key(self, event: events.Key) -> None:
        """Intercept right/left/space to expand or collapse disk sub-rows."""
        try:
            table = self.query_one(DataTable)
            if not table.has_focus:
                return
        except Exception:
            return
        if event.key in ("space", "right"):
            event.stop()
            self._toggle_expand()
        elif event.key == "left":
            event.stop()
            self._collapse_selected()

    def _name_width(self) -> int:
        # Each column gets ~2 chars of padding; widget border/scrollbar ~4 chars
        overhead = _FIXED_SUM + _NUM_COLS * 2 + 4
        return max(_NAME_MIN, self.size.width - overhead)

    def _setup_columns(self) -> None:
        table = self.query_one(DataTable)
        table.clear(columns=True)
        table.add_column("NODE", width=self._name_width())
        for col_name, col_width in _FIXED_COLS:
            table.add_column(col_name, width=col_width)

    def on_cluster_state_updated(self, event: ClusterStateUpdated) -> None:
        self._all_nodes = event.state.nodes
        self._disk_data = event.state.longhorn_disks
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

    def toggle_filter(self) -> None:
        """Toggle pod filter on/off for currently selected node (called by `n` hotkey)."""
        node = self.selected_node
        if node is None:
            return
        if self._filter_node is not None:
            self._filter_node = None
            self.post_message(self.NodeFilterChanged(None))
        else:
            self._filter_node = node.name
            self.post_message(self.NodeFilterChanged(node.name))
        self._rebuild_table()

    def clear_filter(self) -> None:
        """Clear the node filter (called externally)."""
        if self._filter_node is not None:
            self._filter_node = None
            self.post_message(self.NodeFilterChanged(None))
            self._rebuild_table()

    def _toggle_expand(self) -> None:
        node = self.selected_node
        if node is None or node.is_control_plane:
            return
        if node.name not in self._disk_data:
            return
        if node.name in self._expanded_nodes:
            self._expanded_nodes.discard(node.name)
        else:
            self._expanded_nodes.add(node.name)
        self._rebuild_table()

    def _collapse_selected(self) -> None:
        node = self.selected_node
        if node and node.name in self._expanded_nodes:
            self._expanded_nodes.discard(node.name)
            self._rebuild_table()

    def _rebuild_table(self) -> None:
        table = self.query_one(DataTable)
        try:
            cursor_row = table.cursor_row
        except Exception:
            cursor_row = 0

        table.clear()
        self._row_entries = []

        if self._sort_col >= 0:
            nodes = sorted(
                self._all_nodes,
                key=_SORT_KEYS[self._sort_col],
                reverse=self._sort_rev,
            )
        else:
            nodes = sorted(
                self._all_nodes,
                key=lambda n: (n.is_control_plane, n.name),
            )
        self._sorted_nodes = nodes

        for node in nodes:
            bg = row_bg_for_node(node)
            tint = bg is not None

            # Status badge
            status_cell = status_badge_text(node, bg) if tint else status_badge(node)

            # Name with expand indicator and filter highlight
            has_disks = node.name in self._disk_data and not node.is_control_plane
            if has_disks:
                indicator = "▼ " if node.name in self._expanded_nodes else "▶ "
            else:
                indicator = "  "

            if self._filter_node and node.name == self._filter_node:
                name_cell = filter_highlight(indicator + node.name, bg)
            else:
                name_cell = plain_text(indicator + node.name, bg)

            res_val = node.resource or ("ctrl" if node.is_control_plane else "–")
            resource_cell = plain_text(res_val, bg)

            if node.is_control_plane:
                cpu_cell = plain_text("–", bg)
                ram_cell = plain_text("–", bg)
                gpu_cell = plain_text("–", bg)
                disk_cell = plain_text("–", bg)
            else:
                cpu_val = fmt_cpu(node.cpu_requested, node.cpu_allocatable)
                ram_val = fmt_ram_gb(node.ram_requested_gb, node.ram_allocatable_gb)
                if tint:
                    cpu_cell = render_bar_text(
                        node.cpu_requested, node.cpu_allocatable, 10, cpu_val, bg
                    )
                    ram_cell = render_bar_text(
                        node.ram_requested_gb, node.ram_allocatable_gb, 10, ram_val, bg
                    )
                    if node.gpu_allocatable > 0:
                        gpu_cell = render_gpu_bar_text(
                            node.gpu_requested,
                            node.gpu_allocatable,
                            fmt_gpu(node.gpu_requested, node.gpu_allocatable),
                            bg,
                        )
                    else:
                        gpu_cell = plain_text("–", bg)
                else:
                    cpu_cell = render_bar(node.cpu_requested, node.cpu_allocatable, 10, cpu_val)
                    ram_cell = render_bar(
                        node.ram_requested_gb, node.ram_allocatable_gb, 10, ram_val
                    )
                    if node.gpu_allocatable > 0:
                        gpu_cell = render_gpu_bar(
                            node.gpu_requested,
                            node.gpu_allocatable,
                            fmt_gpu(node.gpu_requested, node.gpu_allocatable),
                        )
                    else:
                        gpu_cell = f"[dim]{'–':>29}[/]"

                # Disk aggregate cell — color reflects worst individual disk
                disks = self._disk_data.get(node.name, [])
                if disks:
                    agg_total = sum(d.total_gb for d in disks)
                    agg_avail = sum(d.available_gb for d in disks)
                    agg_used = max(0.0, agg_total - agg_avail)
                    worst_ratio = max(
                        (d.used_gb / d.total_gb for d in disks if d.total_gb > 0),
                        default=0.0,
                    )
                    disk_val = fmt_ram_gb(agg_used, agg_total)
                    if tint:
                        disk_cell = render_bar_text(
                            agg_used, agg_total, 10, disk_val, bg, color_ratio=worst_ratio
                        )
                    else:
                        disk_cell = render_bar(
                            agg_used, agg_total, 10, disk_val, color_ratio=worst_ratio
                        )
                else:
                    disk_cell = plain_text("–", bg)

            table.add_row(
                name_cell,
                resource_cell,
                status_cell,
                disk_cell,
                cpu_cell,
                ram_cell,
                gpu_cell,
                key=node.name,
            )
            self._row_entries.append((node, None))

            # Disk sub-rows when expanded
            if node.name in self._expanded_nodes:
                for disk in self._disk_data.get(node.name, []):
                    disk_bar = render_bar(
                        disk.used_gb,
                        disk.total_gb,
                        10,
                        fmt_ram_gb(disk.used_gb, disk.total_gb),
                    )
                    sched_label = "Sched" if disk.schedulable else "Disab"
                    table.add_row(
                        f"[dim]  └ {disk.name}[/]",
                        f"[dim]{disk.path}[/]",
                        f"[dim]{sched_label}[/]",
                        disk_bar,
                        f"[dim]{'–':>18}[/]",
                        f"[dim]{'–':>18}[/]",
                        f"[dim]{'–':>29}[/]",
                        key=f"{node.name}::{disk.name}",
                    )
                    self._row_entries.append((node, disk))

        total_rows = len(self._row_entries)
        if total_rows > 0:
            row = min(cursor_row, total_rows - 1)
            try:
                table.move_cursor(row=row)
            except Exception:
                pass

    @property
    def selected_node(self) -> "NodeInfo | None":
        if not self._row_entries:
            return None
        try:
            row = self.query_one(DataTable).cursor_row
            if 0 <= row < len(self._row_entries):
                return self._row_entries[row][0]  # always the parent NodeInfo
        except Exception:
            pass
        return None
