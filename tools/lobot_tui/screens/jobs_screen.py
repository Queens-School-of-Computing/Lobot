"""JobsScreen: live background-job output panel."""

from datetime import datetime

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Label, RichLog

from ..config import LOG_DIR
from ..data.job_manager import BackgroundJob, JobCompleted


class JobsScreen(Screen):
    """Shows live streaming output of the current background job."""

    BINDINGS = [
        Binding("b", "go_back", "Background/back", priority=True),
        Binding("k", "kill_job", "Kill job", priority=True),
        Binding("s", "save_output", "Save"),
        # escape and q are handled in on_key so they only work when the job is done
    ]

    def compose(self) -> ComposeResult:
        yield Label("", id="screen-header", markup=True)
        yield RichLog(id="screen-log", highlight=True, markup=False, wrap=True)
        yield Label("", id="screen-footer", markup=True)

    def on_mount(self) -> None:
        self._last_line = 0
        self._kill_pending = False
        self._kill_timer = None
        job = self.app.job_manager.current_job
        self._update_header(job)
        log = self.query_one(RichLog)

        if job is None:
            log.write("No background job has been started yet.")
            self._update_footer(None)
            return

        log.write(f"$ {' '.join(job.argv)}")
        log.write("")
        for line in job.output_lines:
            log.write(line)
        self._last_line = len(job.output_lines)
        self._update_footer(job)

        if job.status == "running":
            self.set_interval(0.25, self._poll_output)

    def _update_header(self, job: "BackgroundJob | None") -> None:
        if job is None:
            text = " [bold cyan]JOBS[/]  [dim]No active job  Esc/q/\[b] close[/]"
        else:
            elapsed = int((datetime.now() - job.start_time).total_seconds())
            status_tag = {
                "running": "[yellow]● Running[/]",
                "done": "[green]✓ Done[/]",
                "failed": "[red]✗ Failed[/]",
            }.get(job.status, "")
            if job.status == "running":
                hint = "\[b] background  \[k] kill (confirm)  \[s] save"
            else:
                hint = "Esc/q/\[b] close  \[s] save"
            text = (
                f" [bold cyan]JOBS[/]  {status_tag}  [dim]{job.title}  "
                f"{elapsed}s elapsed  {hint}[/]"
            )
        self.query_one("#screen-header", Label).update(text)

    def _update_footer(self, job: "BackgroundJob | None") -> None:
        footer = self.query_one("#screen-footer", Label)
        if job is None:
            footer.update("[dim]Esc/q/\[b] close[/]")
        elif job.status == "running":
            footer.update(
                "[dim]\[b] background — job keeps running in dashboard  "
                "\[k] kill job (press twice to confirm)[/]"
            )
        elif job.status == "done":
            footer.update("[green]Completed (exit 0)[/]  [dim]Esc/q/\[b] close  \[s] save[/]")
        else:
            rc = job.returncode if job.returncode is not None else "?"
            footer.update(f"[red]Failed (exit {rc})[/]  [dim]Esc/q/\[b] close  \[s] save[/]")

    def _poll_output(self) -> None:
        job = self.app.job_manager.current_job
        if job is None:
            return
        log = self.query_one(RichLog)
        new_lines = job.output_lines[self._last_line :]
        for line in new_lines:
            log.write(line)
        self._last_line = len(job.output_lines)
        if job.status != "running":
            self._update_header(job)
            self._update_footer(job)

    def on_job_completed(self, event: JobCompleted) -> None:
        """Update display when the job finishes (message re-broadcast from app)."""
        job = event.job
        log = self.query_one(RichLog)
        new_lines = job.output_lines[self._last_line :]
        for line in new_lines:
            log.write(line)
        self._last_line = len(job.output_lines)
        log.write("")
        log.write(
            f"[exit {job.returncode}]" if job.returncode is not None else "[failed to launch]"
        )
        self._update_header(job)
        self._update_footer(job)

    def on_key(self, event) -> None:
        """Allow Escape/q to close the panel only when the job is finished."""
        if event.key in ("escape", "q"):
            job = self.app.job_manager.current_job
            if job is None or job.status != "running":
                event.stop()
                self.app.pop_screen()

    def action_go_back(self) -> None:
        """Background or close this screen — job keeps running if still active."""
        self.app.pop_screen()

    def action_kill_job(self) -> None:
        """Kill the running job — requires a second press within 3 seconds to confirm."""
        job = self.app.job_manager.current_job
        if job is None or job.status != "running":
            return
        if self._kill_pending:
            # Second press — confirmed, kill the job
            self._kill_pending = False
            if self._kill_timer is not None:
                self._kill_timer.stop()
                self._kill_timer = None
            self.app.job_manager.terminate()
            self.notify("Job terminated.", severity="warning")
        else:
            # First press — arm the confirmation
            self._kill_pending = True
            if self._kill_timer is not None:
                self._kill_timer.stop()
            self._kill_timer = self.set_timer(3.0, self._clear_kill_pending)
            self.query_one("#screen-footer", Label).update(
                "[bold red]Press \[k] again within 3 seconds to confirm kill — or wait to cancel[/]"
            )

    def _clear_kill_pending(self) -> None:
        self._kill_pending = False
        self._kill_timer = None
        # Restore normal footer
        job = self.app.job_manager.current_job
        self._update_footer(job)

    def action_save_output(self) -> None:
        from datetime import datetime as _dt

        job = self.app.job_manager.current_job
        if not job or not job.output_lines:
            return
        ts = _dt.now().strftime("%Y%m%d-%H%M%S")
        safe_title = job.title.replace(" ", "-").replace("/", "-")
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = LOG_DIR / f"lobot-tui-{safe_title}-{ts}.log"
        path.write_text(f"$ {' '.join(job.argv)}\n\n" + "\n".join(job.output_lines))
        self.query_one("#screen-footer", Label).update(f"[green]Saved to {path}[/]")
