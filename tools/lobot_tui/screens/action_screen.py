"""ActionScreen: full-screen streaming output for running tools."""

import asyncio
from datetime import datetime
from pathlib import Path

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Label, RichLog

from ..data import command_log


class ActionScreen(Screen):
    """Streams live output of a shell command."""

    BINDINGS = [
        ("escape", "go_back", "Back"),
        ("q", "go_back", "Back"),
        ("s", "save_output", "Save"),
    ]

    def __init__(self, title: str, argv: list, cwd: str = None, auto_close: bool = False) -> None:
        super().__init__()
        self._title = title
        self._argv = argv
        self._cwd = cwd
        self._auto_close = auto_close
        self._output_lines: list[str] = []
        self._proc = None

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
        yield Label("[dim]Running…[/]", id="screen-footer", markup=True)

    def on_mount(self) -> None:
        self.run_worker(self._stream_output(), exclusive=True)

    async def _stream_output(self) -> None:
        log = self.query_one(RichLog)
        footer = self.query_one("#screen-footer", Label)

        log.write(f"$ {' '.join(self._argv)}")
        log.write("")

        try:
            self._proc = await asyncio.create_subprocess_exec(
                *self._argv,
                cwd=self._cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            async for raw_line in self._proc.stdout:
                line = raw_line.decode(errors="replace").rstrip()
                self._output_lines.append(line)
                log.write(line)
            await self._proc.wait()
            rc = self._proc.returncode
            command_log.record(" ".join(self._argv), self._output_lines, rc)
            log.write("")
            log.write(f"[exit {rc}]")
            if self._auto_close:
                await asyncio.sleep(0.8)
                self.app.pop_screen()
            elif rc == 0:
                footer.update("[green]Completed successfully[/]  [dim][Esc/q] back  [s] save[/]")
            else:
                footer.update(f"[red]Exited with code {rc}[/]  [dim][Esc/q] back  [s] save[/]")
        except Exception as e:
            command_log.record(" ".join(self._argv), self._output_lines, None)
            log.write(f"Error: {e}")
            if not self._auto_close:
                footer.update("[red]Command failed to launch[/]")
            else:
                await asyncio.sleep(1.5)
                self.app.pop_screen()

    def action_go_back(self) -> None:
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
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
