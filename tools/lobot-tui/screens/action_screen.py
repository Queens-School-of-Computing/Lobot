"""ActionScreen: full-screen streaming output for running tools."""

from datetime import datetime
from pathlib import Path

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Label, RichLog

from ..actions.runner import run_command


class ActionScreen(Screen):
    """Streams live output of a shell command."""

    BINDINGS = [
        ("escape", "go_back", "Back"),
        ("q", "go_back", "Back"),
        ("s", "save_output", "Save"),
    ]

    def __init__(self, title: str, argv: list, cwd: str = None) -> None:
        super().__init__()
        self._title = title
        self._argv = argv
        self._cwd = cwd
        self._output_lines: list[str] = []
        self._running = True

    def compose(self) -> ComposeResult:
        cmd_display = " ".join(self._argv[:6])
        if len(self._argv) > 6:
            cmd_display += " …"
        yield Label(
            f" [bold cyan]{self._title}[/]  [dim]{cmd_display}[/]  "
            f"[dim][Esc/q] back  [s] save[/]",
            id="screen-header",
            markup=True,
        )
        yield RichLog(id="screen-log", highlight=True, markup=False, wrap=True)
        yield Label("[dim]Running…[/]", id="screen-footer")

    def on_mount(self) -> None:
        self.run_worker(self._stream_output(), exclusive=True)

    async def _stream_output(self) -> None:
        log = self.query_one(RichLog)
        footer = self.query_one("#screen-footer", Label)

        log.write(f"$ {' '.join(self._argv)}")
        log.write("")

        exit_code = None
        try:
            async for line in run_command(self._argv, cwd=self._cwd):
                if line.startswith("[exit "):
                    exit_code = line
                else:
                    self._output_lines.append(line)
                    log.write(line)
        except Exception as e:
            log.write(f"Error launching command: {e}")
            footer.update("[red]Command failed to launch[/]")
            return

        self._running = False
        if exit_code:
            log.write("")
            log.write(exit_code)
            code = exit_code.replace("[exit ", "").replace("]", "")
            if code == "0":
                footer.update(f"[green]Completed successfully[/]  [dim][Esc/q] back  [s] save[/]")
            else:
                footer.update(f"[red]Exited with code {code}[/]  [dim][Esc/q] back  [s] save[/]")

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def action_save_output(self) -> None:
        if not self._output_lines:
            return
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_title = self._title.replace(" ", "-").replace("/", "-")
        path = Path(f"/tmp/lobot-tui-{safe_title}-{ts}.log")
        path.write_text(f"$ {' '.join(self._argv)}\n\n" + "\n".join(self._output_lines))
        footer = self.query_one("#screen-footer", Label)
        footer.update(f"[green]Saved to {path}[/]")
