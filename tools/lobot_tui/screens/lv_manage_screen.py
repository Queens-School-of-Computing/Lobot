"""LvManageScreen: lv-manage.sh output viewer for a PVC or pod."""

import asyncio

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Label, RichLog

from ..config import TOOLS_DIR
from ..data import command_log
from ..widgets.tricolour_stripe import TricolourStripe


class LvManageScreen(Screen):
    """Runs lv-manage.sh against a PVC or pod name and displays the output."""

    BINDINGS = [
        Binding("escape", "go_back", "Back", priority=True),
        Binding("q", "go_back", "Back", priority=True),
    ]

    def __init__(self, name: str, namespace: str) -> None:
        super().__init__()
        self._name = name
        self._namespace = namespace

    def compose(self) -> ComposeResult:
        with Horizontal(id="screen-header"):
            yield Label(
                f" [bold cyan]LV INFO[/]  {self._name}  "
                f"ns:{self._namespace}  [dim][Esc/q] back[/]",
                id="screen-header-main",
                markup=True,
            )
            yield Label("", id="top-bar-cat", markup=False)
        yield TricolourStripe("▄")
        yield RichLog(id="screen-log", highlight=False, markup=False, wrap=False)
        yield Label("[dim]Loading…[/]", id="screen-footer")

    def on_mount(self) -> None:
        self.run_worker(self._load_lv_info(), exclusive=True)

    async def _load_lv_info(self) -> None:
        log = self.query_one(RichLog)
        footer = self.query_one("#screen-footer", Label)

        cmd = [f"{TOOLS_DIR}/lv-manage.sh", self._name, self._namespace]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await proc.communicate()
            for line in stdout.decode(errors="replace").splitlines():
                log.write(Text.from_ansi(line))
            command_log.record(" ".join(cmd), [], proc.returncode)
            footer.update(f"[dim]{self._name} — [Esc/q] back[/]")
        except Exception as e:
            command_log.record(" ".join(cmd), [], None)
            log.write(f"Error: {e}")
            footer.update("[red]Error running lv-manage.sh[/]")

    def action_go_back(self) -> None:
        self.app.pop_screen()
