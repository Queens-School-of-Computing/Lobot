"""GuideScreen: full lobot-tui documentation viewer (lobot-tui.md)."""

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Label, LoadingIndicator, MarkdownViewer

# Resolve path relative to this file: tools/lobot_tui/screens/ → tools/lobot-tui.md
_GUIDE_PATH = Path(__file__).parent.parent.parent / "lobot-tui.md"


class GuideScreen(Screen):
    """Full-screen viewer for lobot-tui.md."""

    BINDINGS = [
        Binding("escape", "go_back", "Back", priority=True),
        Binding("q", "go_back", "Back", priority=True),
    ]

    def compose(self) -> ComposeResult:
        yield Label(
            f" [bold cyan]GUIDE[/]  {_GUIDE_PATH}  [dim][Esc/q] back  [t] table of contents[/]",
            id="screen-header",
            markup=True,
        )
        yield LoadingIndicator(id="guide-loading")

    def on_mount(self) -> None:
        self.call_after_refresh(lambda: self.run_worker(self._load_guide()))

    async def _load_guide(self) -> None:
        try:
            text = _GUIDE_PATH.read_text(encoding="utf-8")
        except OSError as exc:
            text = f"# Error\n\nCould not load `{_GUIDE_PATH}`:\n\n```\n{exc}\n```"
        self.query_one("#guide-loading").display = False
        await self.mount(MarkdownViewer(text, id="guide-viewer", show_table_of_contents=True))

    def action_go_back(self) -> None:
        self.app.pop_screen()
