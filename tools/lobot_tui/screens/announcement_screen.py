"""AnnouncementScreen: structured modal editor for announcement.yaml."""

import asyncio
import re
import urllib.request
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label

from ..config import ANNOUNCEMENT_YAML, HELM_CONFIG_ENV, REPO_DIR
from ..data import command_log

PROD_KEY = "announcement_prod"
DEV_KEY = "announcement_dev"

# Fallback URL if we can't read it from the env config
_FALLBACK_URL = (
    "https://raw.githubusercontent.com/Queens-School-of-Computing/"
    "Lobot/newcluster/announcement.yaml"
)


def _get_announcement_url() -> str:
    """Read LOBOT_ANNOUNCEMENT_URL from the active env config bk file."""
    try:
        text = Path(HELM_CONFIG_ENV).read_text()
        match = re.search(r'LOBOT_ANNOUNCEMENT_URL:\s*"([^"]+)"', text)
        if match:
            return match.group(1).strip()
    except Exception:
        pass
    return _FALLBACK_URL


def _parse_yaml_block(content: str, key: str) -> str:
    """Extract the text value of a YAML block scalar key (> or |)."""
    pattern = rf'^{re.escape(key)}:\s*[>|]\s*\n((?:[ \t]+\S[^\n]*\n?)*)'
    match = re.search(pattern, content, re.MULTILINE)
    if not match:
        plain = re.search(rf'^{re.escape(key)}:\s*(.+)', content, re.MULTILINE)
        return plain.group(1).strip() if plain else ""
    block = match.group(1)
    min_indent = min(
        (len(line) - len(line.lstrip()) for line in block.splitlines() if line.strip()),
        default=2,
    )
    return " ".join(line[min_indent:].strip() for line in block.splitlines() if line.strip())


def _fetch_from_url(url: str) -> tuple[str, str]:
    """Fetch announcement.yaml from a URL and parse both fields."""
    with urllib.request.urlopen(url, timeout=10) as r:
        content = r.read().decode()
    return _parse_yaml_block(content, PROD_KEY), _parse_yaml_block(content, DEV_KEY)


def _load_local_fields() -> tuple[str, str]:
    """Parse the local announcement.yaml as a fallback."""
    try:
        content = Path(ANNOUNCEMENT_YAML).read_text()
        return _parse_yaml_block(content, PROD_KEY), _parse_yaml_block(content, DEV_KEY)
    except Exception:
        return "", ""


def _build_yaml(prod: str, dev: str) -> str:
    """Reconstruct announcement.yaml from the two field values."""

    def block(text: str) -> str:
        return f"  {text.strip()}" if text.strip() else "  "

    return f"{PROD_KEY}: >\n{block(prod)}\n{DEV_KEY}: >\n{block(dev)}\n"


class AnnouncementScreen(ModalScreen):
    """Two-field modal for editing production and dev announcements."""

    BINDINGS = [
        Binding("escape", "go_back", "Cancel", priority=True),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="announcement-dialog"):
            yield Label(
                "[bold cyan]ANNOUNCEMENT EDITOR[/]",
                id="announcement-title",
                markup=True,
            )
            yield Label(
                f"[dim]{ANNOUNCEMENT_YAML}[/]",
                classes="wizard-field-label",
                markup=True,
            )
            yield Label("Production", classes="wizard-field-label")
            yield Input(
                value="",
                placeholder="Loading from GitHub…",
                id="input-prod",
                classes="wizard-input",
            )
            yield Label("Development", classes="wizard-field-label")
            yield Input(
                value="",
                placeholder="Loading from GitHub…",
                id="input-dev",
                classes="wizard-input",
            )
            yield Label(
                "[dim]Fetching current values from GitHub…[/]",
                id="announcement-footer",
                markup=True,
            )
            yield Label(
                "[yellow]⚠ Save & push coming soon — edit announcement.yaml manually for now.[/]",
                classes="wizard-field-label",
                markup=True,
            )
            with Horizontal(id="announcement-buttons"):
                yield Button("Close", variant="default", id="btn-cancel")

    def on_mount(self) -> None:
        self.run_worker(self._load_from_github(), exclusive=False, name="load-announcement")

    async def _load_from_github(self) -> None:
        footer = self.query_one("#announcement-footer", Label)
        url = _get_announcement_url()
        try:
            loop = asyncio.get_running_loop()
            prod, dev = await loop.run_in_executor(None, _fetch_from_url, url)
            self.query_one("#input-prod", Input).value = prod
            self.query_one("#input-dev", Input).value = dev
            footer.update(f"[dim]Loaded from GitHub  ·  Ctrl+S to save and push[/]")
        except Exception as exc:
            # Fall back to local file
            prod, dev = _load_local_fields()
            self.query_one("#input-prod", Input).value = prod
            self.query_one("#input-dev", Input).value = dev
            if prod or dev:
                footer.update(f"[yellow]GitHub unavailable ({exc}) — loaded from local file[/]")
            else:
                footer.update(f"[yellow]Could not load values ({exc}) — fields are empty[/]")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-save":
            self.action_save_and_push()

    def action_go_back(self) -> None:
        self.dismiss(None)

    def action_save_and_push(self) -> None:
        prod = self.query_one("#input-prod", Input).value
        dev = self.query_one("#input-dev", Input).value
        content = _build_yaml(prod, dev)
        self.run_worker(self._save_and_push(content), exclusive=True, name="save-announcement")

    async def _save_and_push(self, content: str) -> None:
        footer = self.query_one("#announcement-footer", Label)
        footer.update("[yellow]Saving…[/]")

        try:
            Path(ANNOUNCEMENT_YAML).write_text(content)
        except Exception as e:
            footer.update(f"[red]Save failed: {e}[/]")
            return

        # Pre-flight: verify REPO_DIR is a git repository
        rc, lines = await self._run_git(["git", "rev-parse", "--show-toplevel"])
        if rc != 0:
            detail = lines[0] if lines else "no output"
            footer.update(f"[red]Not a git repository: {REPO_DIR}\n{detail}[/]")
            return

        footer.update("[yellow]Committing and pushing…[/]")

        # git add
        rc, lines = await self._run_git(["git", "add", ANNOUNCEMENT_YAML])
        command_log.record(f"git add {ANNOUNCEMENT_YAML}", lines, rc)
        if rc != 0:
            detail = lines[0] if lines else "no output"
            footer.update(f"[red]git add failed (exit {rc}): {detail}[/]")
            return

        # Check if there is anything to commit
        rc_status, status_lines = await self._run_git(
            ["git", "status", "--porcelain", ANNOUNCEMENT_YAML]
        )
        if rc_status == 0 and not any(l.strip() for l in status_lines):
            footer.update("[dim]No changes — file already up to date. Pushing anyway…[/]")
        else:
            rc, lines = await self._run_git(
                ["git", "commit", "-m", "chore: update announcement via lobot-tui"]
            )
            command_log.record("git commit", lines, rc)
            if rc != 0:
                detail = lines[0] if lines else "no output"
                footer.update(f"[red]git commit failed (exit {rc}): {detail}[/]")
                return

        rc, lines = await self._run_git(["git", "push", "origin", "newcluster"])
        command_log.record("git push origin newcluster", lines, rc)
        if rc != 0:
            detail = lines[0] if lines else "no output"
            footer.update(f"[red]git push failed (exit {rc}): {detail}[/]")
            return

        footer.update("[green]Saved and pushed to GitHub successfully![/]")

    async def _run_git(self, cmd: list) -> tuple:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=REPO_DIR,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        lines = stdout.decode(errors="replace").splitlines()
        return proc.returncode, lines
