"""LogsScreen: full-screen streaming pod log viewer."""

import asyncio
from datetime import datetime
from pathlib import Path

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Label, RichLog

from ..data import command_log
from ..data.models import PodInfo


class LogsScreen(Screen):
    """Streams kubectl logs -f for a selected pod."""

    BINDINGS = [
        ("escape", "go_back", "Back"),
        ("q", "go_back", "Back"),
        ("s", "save_log", "Save"),
    ]

    def __init__(self, pod: PodInfo) -> None:
        super().__init__()
        self._pod = pod
        self._proc = None
        self._log_lines: list[str] = []

    def compose(self) -> ComposeResult:
        yield Label(
            f" [bold cyan]LOGS[/]  {self._pod.name}  ns:{self._pod.namespace}  "
            f"[dim][Esc/q] back  [s] save[/]",
            id="screen-header",
            markup=True,
        )
        yield RichLog(id="screen-log", highlight=True, markup=True, wrap=True)
        yield Label("", id="screen-footer")

    def on_mount(self) -> None:
        self.run_worker(self._stream_logs(), exclusive=True)

    async def _stream_logs(self) -> None:
        log = self.query_one(RichLog)
        footer = self.query_one("#screen-footer", Label)
        footer.update("[dim]Connecting…[/]")

        cmd = [
            "kubectl", "logs", "-f",
            self._pod.name,
            "-n", self._pod.namespace,
            "--tail", "500",
        ]
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            footer.update(
                f"[dim]Streaming logs — {self._pod.name}[/]"
            )
            async for raw_line in self._proc.stdout:
                line = raw_line.decode(errors="replace").rstrip()
                self._log_lines.append(line)
                log.write(line)
        except Exception as e:
            log.write(f"[red]Error: {e}[/]")
        finally:
            if self._proc:
                await self._proc.wait()
            rc = self._proc.returncode if self._proc else None
            command_log.record(" ".join(cmd), [f"[{len(self._log_lines)} lines streamed]"], rc)
            footer.update("[dim]Stream ended — [Esc/q] back  [s] save[/]")

    def action_go_back(self) -> None:
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
        self.app.pop_screen()

    def action_save_log(self) -> None:
        if not self._log_lines:
            return
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = Path(f"/tmp/lobot-tui-logs-{self._pod.username}-{ts}.log")
        path.write_text("\n".join(self._log_lines))
        footer = self.query_one("#screen-footer", Label)
        footer.update(f"[green]Saved to {path}[/]")
