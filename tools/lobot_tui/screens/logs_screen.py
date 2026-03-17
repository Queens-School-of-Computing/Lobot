"""LogsScreen: full-screen streaming pod log viewer."""

import asyncio
from datetime import datetime

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Label, RichLog

from ..config import LOG_DIR
from ..data import command_log
from ..data.models import PodInfo

_FOOTER_LIVE = r"[dim]Streaming — \[Esc/q] back  \[s] save  (scroll up to pause)[/]"
_FOOTER_PAUSED = r"[yellow]⏸ Paused — \[l] resume stream  \[s] save  \[Esc/q] back[/]"
_FOOTER_ENDED = r"[dim]Stream ended — \[Esc/q] back  \[s] save[/]"
_FOOTER_ENDED_PAUSED = r"[dim]Stream ended (was paused) — \[Esc/q] back  \[s] save[/]"


class LogsScreen(Screen):
    """Streams kubectl logs -f for a selected pod."""

    BINDINGS = [
        Binding("escape", "go_back", "Back", priority=True),
        Binding("q", "go_back", "Back", priority=True),
        Binding("l", "resume_stream", "Resume stream"),
        Binding("up", "scroll_up_key", show=False, priority=True),
        Binding("pageup", "scroll_pageup_key", show=False, priority=True),
        ("s", "save_log", "Save"),
    ]

    def __init__(self, pod: PodInfo) -> None:
        super().__init__()
        self._pod = pod
        self._proc = None
        self._log_lines: list[str] = []
        self._paused = False
        self._buffered_lines: list[str] = []
        self._stream_done = False

    def compose(self) -> ComposeResult:
        yield Label(
            f" [bold cyan]LOGS[/]  {self._pod.name}  ns:{self._pod.namespace}  "
            rf"[dim]\[Esc/q] back  \[s] save[/]",
            id="screen-header",
            markup=True,
        )
        yield RichLog(id="screen-log", highlight=True, markup=True, wrap=True)
        yield Label("", id="screen-footer")

    def on_mount(self) -> None:
        self.run_worker(self._stream_logs(), exclusive=True)
        # Watch the RichLog's scroll_y reactive so we detect all scroll input
        # (mouse wheel, trackpad, arrow keys) without relying on event bubbling.
        log = self.query_one(RichLog)
        self.watch(log, "scroll_y", self._on_log_scroll_y_changed)

    # ── Scroll detection ───────────────────────────────────────────────────

    def _on_log_scroll_y_changed(self, scroll_y: float) -> None:
        """Fire whenever RichLog.scroll_y changes. Pause if user scrolled up."""
        if self._paused or self._stream_done:
            return
        try:
            log = self.query_one(RichLog)
            # auto_scroll sets scroll_target_y = max_scroll_y after each write,
            # so when auto_scroll has settled, scroll_y ≈ max_scroll_y.
            # A gap > 2 lines means the user has deliberately scrolled up.
            if scroll_y < log.max_scroll_y - 2:
                self._trigger_pause()
        except Exception:
            pass

    def _trigger_pause(self) -> None:
        self._paused = True
        self.query_one("#screen-footer", Label).update(_FOOTER_PAUSED)

    # ── Keyboard scroll (priority bindings so RichLog doesn't consume them) ─

    def action_scroll_up_key(self) -> None:
        self.query_one(RichLog).scroll_up(animate=False)

    def action_scroll_pageup_key(self) -> None:
        self.query_one(RichLog).scroll_page_up(animate=False)

    # ── Streaming ──────────────────────────────────────────────────────────

    async def _stream_logs(self) -> None:
        log = self.query_one(RichLog)
        footer = self.query_one("#screen-footer", Label)
        footer.update("[dim]Connecting…[/]")

        cmd = [
            "kubectl",
            "logs",
            "-f",
            self._pod.name,
            "-n",
            self._pod.namespace,
            "--tail",
            "500",
        ]
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            if not self._paused:
                footer.update(_FOOTER_LIVE)
            async for raw_line in self._proc.stdout:
                line = raw_line.decode(errors="replace").rstrip()
                self._log_lines.append(line)
                if self._paused:
                    self._buffered_lines.append(line)
                else:
                    log.write(line)
        except Exception as e:
            log.write(f"[red]Error: {e}[/]")
        finally:
            if self._proc:
                await self._proc.wait()
            rc = self._proc.returncode if self._proc else None
            command_log.record(" ".join(cmd), [], rc)
            self._stream_done = True
            footer.update(_FOOTER_ENDED_PAUSED if self._paused else _FOOTER_ENDED)

    # ── Resume ─────────────────────────────────────────────────────────────

    def action_resume_stream(self) -> None:
        """Flush buffered lines, scroll to bottom, and resume live display."""
        if not self._paused:
            return
        self._paused = False
        log = self.query_one(RichLog)
        for line in self._buffered_lines:
            log.write(line)
        self._buffered_lines.clear()
        log.scroll_end(animate=False)
        self.query_one("#screen-footer", Label).update(
            _FOOTER_ENDED if self._stream_done else _FOOTER_LIVE
        )

    # ── Navigation / save ──────────────────────────────────────────────────

    def action_go_back(self) -> None:
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
        self.app.pop_screen()

    def action_save_log(self) -> None:
        if not self._log_lines:
            return
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = LOG_DIR / f"lobot-tui-logs-{self._pod.username}-{ts}.log"
        path.write_text("\n".join(self._log_lines))
        self.query_one("#screen-footer", Label).update(f"[green]Saved to {path}[/]")
