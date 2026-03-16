"""NodeTable: DataTable widget showing cluster nodes."""

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import DataTable

from ..data.collector import ClusterStateUpdated
from ..data.models import NodeInfo

# Fixed-width columns (excluding NAME which expands)
_FIXED_COLS = [
    ("RESOURCE", 20),
    ("STATUS", 10),
    ("CPU",     9),
    ("RAM",    15),
    ("GPU",     7),
]
_NUM_COLS = len(_FIXED_COLS) + 1  # including NAME
_FIXED_SUM = sum(w for _, w in _FIXED_COLS)
_NAME_MIN = 16

# Sort key functions indexed by column (0=NAME, then _FIXED_COLS order)
def _status_order(n: NodeInfo) -> int:
    if n.is_control_plane:         return 0
    if n.status == "Ready" and n.schedulable:   return 1
    if n.status == "Ready" and not n.schedulable: return 2
    if n.status == "NotReady":     return 3
    return 4

_SORT_KEYS = [
    lambda n: n.name,
    lambda n: n.resource or "",
    _status_order,
    lambda n: n.cpu_requested,
    lambda n: n.ram_requested_gb,
    lambda n: n.gpu_requested,
]


def _status_markup(node: NodeInfo) -> str:
    if node.is_control_plane:
        return "[dim]ctrl-plane[/]"
    if node.status == "Ready" and node.schedulable:
        return "[green]Ready[/]"
    if node.status == "Ready" and not node.schedulable:
        return "[yellow]Cordoned[/]"
    if node.status == "NotReady":
        return "[red]NotReady[/]"
    return "[dim]Unknown[/]"


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
    _filter_node: "str | None" = None   # node name actively filtering pods

    def compose(self) -> ComposeResult:
        yield DataTable(id="node-datatable", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        self._setup_columns()

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
        """Toggle pod filter on/off for currently selected node (called by `.` hotkey)."""
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

    def _rebuild_table(self) -> None:
        table = self.query_one(DataTable)
        try:
            cursor_row = table.cursor_row
        except Exception:
            cursor_row = 0

        table.clear()

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
            status = _status_markup(node)
            if node.is_control_plane:
                cpu_str = "[dim]–[/]"
                ram_str = "[dim]–[/]"
                gpu_str = "[dim]–[/]"
            else:
                cpu_str = f"{node.cpu_requested}/{node.cpu_allocatable}"
                ram_str = f"{node.ram_requested_gb:.1f}/{node.ram_allocatable_gb:.1f}G"
                if node.gpu_allocatable > 0:
                    gpu_str = f"{node.gpu_requested}/{node.gpu_allocatable}"
                else:
                    gpu_str = "–"

            # Highlight the node currently being used to filter pods
            name_display = node.name
            if self._filter_node and node.name == self._filter_node:
                name_display = f"[bold cyan]{node.name}[/]"

            table.add_row(
                name_display,
                node.resource or ("ctrl" if node.is_control_plane else "–"),
                status,
                cpu_str,
                ram_str,
                gpu_str,
                key=node.name,
            )

        if self._all_nodes:
            row = min(cursor_row, len(nodes) - 1)
            try:
                table.move_cursor(row=row)
            except Exception:
                pass

    @property
    def selected_node(self) -> "NodeInfo | None":
        table = self.query_one(DataTable)
        nodes = self._sorted_nodes or sorted(
            self._all_nodes, key=lambda n: (n.is_control_plane, n.name)
        )
        if not nodes:
            return None
        try:
            row = table.cursor_row
            if 0 <= row < len(nodes):
                return nodes[row]
        except Exception:
            pass
        return None
