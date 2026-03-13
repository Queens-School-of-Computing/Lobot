"""NodeTable: DataTable widget showing cluster nodes."""

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable

from ..data.collector import ClusterStateUpdated
from ..data.models import ClusterState, NodeInfo

COLUMNS = [
    ("NAME", 22),
    ("LAB", 14),
    ("STATUS", 10),
    ("CPU", 9),
    ("RAM", 11),
    ("GPU", 7),
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

    _all_nodes: list = []

    def compose(self) -> ComposeResult:
        yield DataTable(id="node-datatable", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        for col_name, col_width in COLUMNS:
            table.add_column(col_name, width=col_width)

    def on_cluster_state_updated(self, event: ClusterStateUpdated) -> None:
        self._all_nodes = event.state.nodes
        self._rebuild_table()

    def _rebuild_table(self) -> None:
        table = self.query_one(DataTable)
        try:
            cursor_row = table.cursor_row
        except Exception:
            cursor_row = 0

        table.clear()

        # Sort: control plane last, then alphabetical
        nodes = sorted(
            self._all_nodes,
            key=lambda n: (n.is_control_plane, n.name)
        )

        for node in nodes:
            status = _status_markup(node)
            if node.is_control_plane:
                cpu_str = "[dim]–[/]"
                ram_str = "[dim]–[/]"
                gpu_str = "[dim]–[/]"
            else:
                cpu_str = f"{node.cpu_requested}/{node.cpu_allocatable}"
                ram_str = f"{node.ram_requested_gb}/{node.ram_allocatable_gb}G"
                if node.gpu_allocatable > 0:
                    gpu_str = f"{node.gpu_requested}/{node.gpu_allocatable}"
                else:
                    gpu_str = "–"

            table.add_row(
                node.name,
                node.lab or ("ctrl" if node.is_control_plane else "–"),
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
        nodes_sorted = sorted(
            self._all_nodes,
            key=lambda n: (n.is_control_plane, n.name)
        )
        if not nodes_sorted:
            return None
        try:
            row = table.cursor_row
            if 0 <= row < len(nodes_sorted):
                return nodes_sorted[row]
        except Exception:
            pass
        return None
