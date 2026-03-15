"""BackgroundJobManager: runs a single long-lived tool command in the background."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

from textual.message import Message

from . import command_log


@dataclass
class BackgroundJob:
    title: str
    argv: list
    cwd: str | None
    start_time: datetime = field(default_factory=datetime.now)
    output_lines: list = field(default_factory=list)
    status: str = "running"   # running | done | failed
    returncode: int | None = None
    _proc: object = field(default=None, repr=False)


class JobCompleted(Message):
    """Posted to the app when a background job finishes."""
    def __init__(self, job: BackgroundJob) -> None:
        super().__init__()
        self.job = job


class BackgroundJobManager:
    """Holds at most one background job at a time."""

    def __init__(self) -> None:
        self._job: BackgroundJob | None = None

    @property
    def current_job(self) -> BackgroundJob | None:
        return self._job

    @property
    def is_running(self) -> bool:
        return self._job is not None and self._job.status == "running"

    def start(self, app, title: str, argv: list, cwd: str | None) -> BackgroundJob:
        """Launch argv as a background subprocess. Returns the new job."""
        self._job = BackgroundJob(title=title, argv=argv, cwd=cwd)
        asyncio.ensure_future(self._run(app, self._job))
        return self._job

    async def _run(self, app, job: BackgroundJob) -> None:
        try:
            job._proc = await asyncio.create_subprocess_exec(
                *job.argv,
                cwd=job.cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            async for raw_line in job._proc.stdout:
                line = raw_line.decode(errors="replace").rstrip()
                job.output_lines.append(line)
            await job._proc.wait()
            job.returncode = job._proc.returncode
            job.status = "done" if job.returncode == 0 else "failed"
            command_log.record(" ".join(job.argv), [], job.returncode)
        except Exception as e:
            job.status = "failed"
            job.output_lines.append(f"Error launching job: {e}")
            command_log.record(" ".join(job.argv), [], None)
        app.post_message(JobCompleted(job))

    def terminate(self) -> None:
        """Terminate the running background job."""
        if self._job and self._job._proc and self._job.status == "running":
            try:
                self._job._proc.terminate()
            except Exception:
                pass
