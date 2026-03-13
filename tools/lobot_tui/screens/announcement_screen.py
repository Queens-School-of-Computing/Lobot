"""AnnouncementScreen: YAML editor + git push for announcement.yaml."""

import asyncio
from pathlib import Path

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Label, RichLog, TextArea

from ..config import ANNOUNCEMENT_YAML, REPO_DIR
from ..data import command_log


class AnnouncementScreen(Screen):
    """Edit announcement.yaml and push to GitHub."""

    BINDINGS = [
        ("escape", "go_back", "Back"),
        ("ctrl+s", "save_and_push", "Save & Push"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._path = Path(ANNOUNCEMENT_YAML)

    def compose(self) -> ComposeResult:
        yield Label(
            " [bold cyan]ANNOUNCEMENT EDITOR[/]  "
            "[dim][Ctrl+S] save & push to GitHub  [Esc] back[/]",
            id="announcement-header",
            markup=True,
        )
        content = self._load_file()
        yield TextArea(content, id="announcement-editor", language="yaml")
        yield Label("[dim]Waiting — Ctrl+S to save and push[/]", id="announcement-footer")

    def _load_file(self) -> str:
        try:
            return self._path.read_text()
        except FileNotFoundError:
            return (
                "announcement_prod: >\n"
                "  Your announcement here.\n"
                "announcement_dev: >\n"
                "  Dev announcement here.\n"
            )
        except Exception as e:
            return f"# Error loading file: {e}\n"

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def action_save_and_push(self) -> None:
        editor = self.query_one(TextArea)
        content = editor.text
        self.run_worker(self._save_and_push(content), exclusive=True)

    async def _save_and_push(self, content: str) -> None:
        footer = self.query_one("#announcement-footer", Label)
        footer.update("[yellow]Saving…[/]")

        try:
            self._path.write_text(content)
        except Exception as e:
            footer.update(f"[red]Save failed: {e}[/]")
            return

        footer.update("[yellow]Committing and pushing…[/]")

        git_commands = [
            ["git", "add", str(self._path)],
            ["git", "commit", "-m", "chore: update announcement via lobot-tui"],
            ["git", "push", "origin", "newcluster"],
        ]

        for cmd in git_commands:
            rc, out = await self._run_git(cmd)
            command_log.record(" ".join(cmd), out, rc)
            if rc != 0:
                footer.update(f"[red]Git command failed: {' '.join(cmd)}[/]")
                return

        footer.update("[green]Saved and pushed to GitHub successfully![/]")

    async def _run_git(self, cmd: list) -> tuple[int, list[str]]:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=REPO_DIR,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        lines = stdout.decode(errors="replace").splitlines()
        return proc.returncode, lines
