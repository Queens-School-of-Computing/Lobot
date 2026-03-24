"""PodDetailScreen: kubectl describe pod viewer."""

import asyncio

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Label, RichLog

from ..data import command_log
from ..data.models import PodInfo
from ..widgets.tricolour_stripe import TricolourStripe


class PodDetailScreen(Screen):
    """Shows kubectl describe pod output for the selected pod."""

    BINDINGS = [
        Binding("escape", "go_back", "Back", priority=True),
        Binding("q", "go_back", "Back", priority=True),
    ]

    def __init__(self, pod: PodInfo) -> None:
        super().__init__()
        self._pod = pod

    def compose(self) -> ComposeResult:
        with Horizontal(id="screen-header"):
            yield Label(
                f" [bold cyan]DESCRIBE[/]  {self._pod.name}  "
                f"ns:{self._pod.namespace}  [dim][Esc/q] back[/]",
                id="screen-header-main",
                markup=True,
            )
            yield Label("", id="top-bar-cat", markup=False)
        yield TricolourStripe("▄")
        yield RichLog(id="screen-log", highlight=False, markup=False, wrap=False)
        yield Label("[dim]Loading…[/]", id="screen-footer")

    def on_mount(self) -> None:
        self.run_worker(self._load_describe(), exclusive=True)

    async def _load_describe(self) -> None:
        log = self.query_one(RichLog)
        footer = self.query_one("#screen-footer", Label)

        cmd = ["kubectl", "describe", "pod", self._pod.name, "-n", self._pod.namespace]
        lines: list[str] = []
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await proc.communicate()
            text = stdout.decode(errors="replace")
            lines = text.splitlines()
            for line in lines:
                log.write(line)
            command_log.record(" ".join(cmd), [], proc.returncode)
            footer.update(f"[dim]{self._pod.name} — [Esc/q] back[/]")
        except Exception as e:
            command_log.record(" ".join(cmd), [], None)
            log.write(f"Error: {e}")
            footer.update("[red]Error loading describe output[/]")

    def action_go_back(self) -> None:
        self.app.pop_screen()
