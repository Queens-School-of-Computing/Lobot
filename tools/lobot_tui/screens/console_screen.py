"""ConsoleScreen: log of all commands run and their exit codes."""

from datetime import datetime

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Label, RichLog

from ..config import LOG_DIR
from ..data import command_log


class ConsoleScreen(Screen):
    """Shows the history of all commands run in this session."""

    BINDINGS = [
        ("escape", "go_back", "Back"),
        ("q", "go_back", "Back"),
        ("grave_accent", "go_back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        log_file = LOG_DIR / f"lobot-tui-{datetime.now().strftime('%Y-%m-%d')}.log"
        yield Label(
            f" [bold cyan]CONSOLE[/]  [dim]command history  "
            f"log: {log_file}  [Esc/q/`] back[/]",
            id="screen-header",
            markup=True,
        )
        yield RichLog(id="screen-log", highlight=False, markup=True, wrap=True)
        yield Label("[dim]Most recent commands first[/]", id="screen-footer", markup=True)

    def on_mount(self) -> None:
        log = self.query_one(RichLog)
        entries = command_log.entries()
        if not entries:
            log.write("[dim]No commands run yet in this session.[/]")
            return
        for entry in entries:
            code = entry["exit_code"]
            if code is None:
                code_str = "[red]failed to launch[/]"
            elif code == 0:
                code_str = "[green]exit 0[/]"
            else:
                code_str = f"[red]exit {code}[/]"
            log.write(f"[dim]{entry['ts']}[/]  {code_str}  [bold]{entry['command']}[/]")
            for line in entry["lines"][-10:]:
                log.write(f"  [dim]{line}[/]")
            log.write("")

    def action_go_back(self) -> None:
        self.app.pop_screen()
