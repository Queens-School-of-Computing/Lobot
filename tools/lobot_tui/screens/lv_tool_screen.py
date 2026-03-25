"""LvToolScreen: PVC picker for offline volume management."""

import asyncio
import json

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import DataTable, Label

from ..data import command_log
from ..widgets.tricolour_stripe import TricolourStripe
from .lv_expand_screen import LvExpandScreen
from .lv_manage_screen import LvManageScreen


class LvToolScreen(Screen):
    """Lists all PVCs and lets the user view info or expand one."""

    BINDINGS = [
        Binding("escape", "go_back", "Back", priority=True),
        Binding("q", "go_back", "Back", priority=True),
        Binding("i", "lv_info", "Info"),
        Binding("enter", "lv_info", "Info", priority=True),
        Binding("E", "lv_expand", "Expand"),
    ]

    def compose(self) -> ComposeResult:
        with Horizontal(id="screen-header"):
            yield Label(
                " [bold cyan]LV TOOL[/]  Select a PVC  "
                "[dim][i/Enter] info  [E] expand  [Esc/q] back[/]",
                id="screen-header-main",
                markup=True,
            )
            yield Label("", id="top-bar-cat", markup=False)
        yield TricolourStripe("▄")
        yield DataTable(id="pvc-table", cursor_type="row", zebra_stripes=True)
        yield Label("[dim]Loading PVCs…[/]", id="screen-footer", markup=True)

    def on_mount(self) -> None:
        table = self.query_one("#pvc-table", DataTable)
        table.add_columns("PVC NAME", "NAMESPACE", "CAPACITY", "STATUS", "STORAGE CLASS", "ACCESS MODE")
        self.run_worker(self._load_pvcs(), exclusive=True)

    async def _load_pvcs(self) -> None:
        table = self.query_one("#pvc-table", DataTable)
        footer = self.query_one("#screen-footer", Label)

        cmd = ["kubectl", "get", "pvc", "-A", "-o", "json"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            command_log.record(" ".join(cmd), [], proc.returncode)

            data = json.loads(stdout.decode(errors="replace"))
            items = sorted(
                data.get("items", []),
                key=lambda p: (p["metadata"]["namespace"], p["metadata"]["name"]),
            )

            for item in items:
                name      = item["metadata"]["name"]
                namespace = item["metadata"]["namespace"]
                capacity  = item.get("status", {}).get("capacity", {}).get("storage", "—")
                status    = item.get("status", {}).get("phase", "—")
                sc        = item["spec"].get("storageClassName", "—")
                access    = ", ".join(item["spec"].get("accessModes", []))
                # Store name|namespace in the row key for retrieval
                table.add_row(name, namespace, capacity, status, sc, access,
                              key=f"{name}|{namespace}")

            count = len(items)
            footer.update(
                f"[dim]{count} PVC{'s' if count != 1 else ''}  —  "
                "[bold]i/Enter[/bold] info  [bold]E[/bold] expand  [bold]Esc/q[/bold] back[/]"
            )
            if count:
                table.focus()
        except Exception as ex:
            footer.update(f"[red]Error loading PVCs: {ex}[/]")

    def _selected(self) -> tuple[str, str] | None:
        table = self.query_one("#pvc-table", DataTable)
        if table.row_count == 0:
            return None
        row_key = table.get_row_at(table.cursor_row)
        # row_key[0] is the PVC name cell value; retrieve name|namespace from key
        key = table.cursor_row  # use coordinate to get the row key object
        rk = table.get_row_at(table.cursor_row)
        # row data: [name, namespace, ...]
        return str(rk[0]), str(rk[1])

    def action_lv_info(self) -> None:
        sel = self._selected()
        if sel:
            self.app.push_screen(LvManageScreen(sel[0], sel[1]))

    def action_lv_expand(self) -> None:
        sel = self._selected()
        if sel:
            self.app.push_screen(LvExpandScreen(sel[0], sel[1]))

    def action_go_back(self) -> None:
        self.app.pop_screen()
