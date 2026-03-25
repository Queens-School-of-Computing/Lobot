"""LvExpandScreen: interactive volume expansion via lv-manage.sh."""

import asyncio
import re

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Input, Label, RichLog

from ..config import TOOLS_DIR
from ..data import command_log
from ..widgets.tricolour_stripe import TricolourStripe

_SIZE_RE = re.compile(r"^\d+[MGT]$", re.IGNORECASE)

# Phase progression:
#   loading       — running lv-manage.sh for info display
#   awaiting_size — info shown, Input widget visible, user enters new size
#   confirming    — size entered, user must press Enter to proceed or Esc to cancel
#   expanding     — running lv-manage.sh --expand SIZE --yes
#   done          — expansion finished (success or blocked)


class LvExpandScreen(Screen):
    """Shows LV info for the selected pod, then lets the user expand a volume."""

    BINDINGS = [
        Binding("escape", "go_back", "Back / Cancel", priority=True),
        Binding("q", "go_back", "Back / Cancel", priority=True),
    ]

    _phase: reactive[str] = reactive("loading")

    def __init__(self, name: str, namespace: str) -> None:
        super().__init__()
        self._name = name
        self._namespace = namespace
        self._expand_size: str = ""

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Horizontal(id="screen-header"):
            yield Label(
                f" [bold cyan]LV EXPAND[/]  {self._name}  "
                f"ns:{self._namespace}  [dim][Esc] back[/]",
                id="screen-header-main",
                markup=True,
            )
            yield Label("", id="top-bar-cat", markup=False)
        yield TricolourStripe("▄")
        yield RichLog(id="screen-log", highlight=False, markup=False, wrap=False)
        yield Input(
            placeholder="New size — e.g. 100G, 500M, 2T",
            id="size-input",
        )
        yield Label("[dim]Loading volume info…[/]", id="screen-footer", markup=True)

    def on_mount(self) -> None:
        self.query_one("#size-input", Input).display = False
        self.run_worker(self._load_info(), exclusive=True)

    # ------------------------------------------------------------------
    # Phase helpers
    # ------------------------------------------------------------------

    def _set_footer(self, text: str) -> None:
        self.query_one("#screen-footer", Label).update(text)

    def _append(self, line: str) -> None:
        self.query_one(RichLog).write(Text.from_ansi(line))

    def _divider(self) -> None:
        self.query_one(RichLog).write(
            Text.from_ansi("\033[2m" + "─" * 64 + "\033[0m")
        )

    # ------------------------------------------------------------------
    # Phase 1 — load info
    # ------------------------------------------------------------------

    async def _load_info(self) -> None:
        cmd = [f"{TOOLS_DIR}/lv-manage.sh", self._name, self._namespace]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await proc.communicate()
            for line in stdout.decode(errors="replace").splitlines():
                self._append(line)
            command_log.record(" ".join(cmd), [], proc.returncode)
        except Exception as e:
            self._append(f"Error loading info: {e}")

        # Transition → awaiting_size
        self._divider()
        inp = self.query_one("#size-input", Input)
        inp.display = True
        inp.focus()
        self._phase = "awaiting_size"
        self._set_footer(
            "[dim]Enter new size and press [bold]Enter[/bold], or [bold]Esc[/bold] to cancel[/]"
        )

    # ------------------------------------------------------------------
    # Phase 2 — size submitted
    # ------------------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._phase != "awaiting_size":
            return

        size = event.value.strip().upper()
        if not _SIZE_RE.match(size):
            self._set_footer(
                "[red]Invalid size — use a number followed by M, G, or T "
                "(e.g. 100G, 500M, 2T)[/]"
            )
            return

        self._expand_size = size
        self.query_one("#size-input", Input).display = False
        self._phase = "confirming"
        self._set_footer(
            f"Expand to [bold cyan]{size}[/]?  "
            "[bold]Enter[/bold] to confirm  [bold]Esc[/bold] to cancel"
        )

    # ------------------------------------------------------------------
    # Phase 3 — confirmation key
    # ------------------------------------------------------------------

    def on_key(self, event) -> None:
        if self._phase == "confirming" and event.key == "enter":
            event.stop()
            self.run_worker(self._do_expand(), exclusive=True)
        elif self._phase == "done" and event.key in ("escape", "q"):
            event.stop()
            self.app.pop_screen()

    # ------------------------------------------------------------------
    # Phase 4 — run expansion
    # ------------------------------------------------------------------

    async def _do_expand(self) -> None:
        self._phase = "expanding"
        self._set_footer("[dim]Expanding…[/]")
        self._divider()

        cmd = [
            f"{TOOLS_DIR}/lv-manage.sh",
            self._name,
            self._namespace,
            "--expand", self._expand_size,
            "--yes",
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await proc.communicate()
            for line in stdout.decode(errors="replace").splitlines():
                self._append(line)
            command_log.record(" ".join(cmd), [], proc.returncode)

            if proc.returncode == 0:
                self._set_footer(
                    f"[green]Expansion to {self._expand_size} complete.[/]  "
                    "[dim][Esc/q] back[/]"
                )
            else:
                self._set_footer(
                    "[red]Expansion blocked or failed.[/]  [dim][Esc/q] back[/]"
                )
        except Exception as e:
            self._append(f"Error: {e}")
            self._set_footer("[red]Expansion error.[/]  [dim][Esc/q] back[/]")

        self._phase = "done"

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def action_go_back(self) -> None:
        if self._phase in ("loading", "expanding"):
            return  # don't allow exit while work is in flight
        self.app.pop_screen()
