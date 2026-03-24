"""GuideScreen: full lobot-tui documentation viewer (lobot-tui.md)."""

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Label, LoadingIndicator, Markdown, MarkdownViewer

from ..widgets.tricolour_stripe import TricolourStripe

# Resolve path relative to this file: tools/lobot_tui/screens/ → tools/lobot-tui.md
_GUIDE_PATH = Path(__file__).parent.parent.parent / "lobot-tui.md"


class GuideScreen(Screen):
    """Full-screen markdown viewer. Defaults to lobot-tui.md; pass path/label to view other docs."""

    BINDINGS = [
        Binding("escape", "go_back", "Back", priority=True),
        Binding("q", "go_back", "Back", priority=True),
    ]

    def __init__(self, path: Path | None = None, label: str = "GUIDE") -> None:
        super().__init__()
        self._path = path or _GUIDE_PATH
        self._label = label
        self._scroll_restore: float | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="screen-header"):
            yield Label(
                f" [bold cyan]{self._label}[/]  {self._path}  [dim][Esc/q] back  [t] table of contents[/]",
                id="screen-header-main",
                markup=True,
            )
            yield Label("", id="top-bar-cat", markup=False)
        yield TricolourStripe("▄")
        yield LoadingIndicator(id="guide-loading")

    def on_mount(self) -> None:
        self.call_after_refresh(lambda: self.run_worker(self._load_guide()))

    async def _load_guide(self) -> None:
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError as exc:
            text = f"# Error\n\nCould not load `{self._path}`:\n\n```\n{exc}\n```"
        self.query_one("#guide-loading").display = False
        await self.mount(MarkdownViewer(text, id="guide-viewer", show_table_of_contents=True))
        # Focus the document pane (not the TOC) by default
        try:
            self.query_one("#guide-viewer").query_one(Markdown).focus()
        except Exception:
            self.query_one("#guide-viewer").focus()

    def on_descendant_focus(self, event) -> None:
        """When the Markdown content pane gains focus, preserve the scroll position.

        Textual's focus mechanism calls scroll_visible() on the newly focused widget,
        which scrolls the MarkdownViewer back to the top of the document. We capture
        the scroll position before that happens and restore it after the next render.
        """
        if isinstance(event.widget, Markdown):
            try:
                viewer = self.query_one(MarkdownViewer)
                self._scroll_restore = viewer.scroll_y
                def _restore():
                    if self._scroll_restore is not None:
                        viewer.scroll_to(y=self._scroll_restore, animate=False)
                        self._scroll_restore = None
                self.call_after_refresh(lambda: self.call_after_refresh(_restore))
            except Exception:
                pass

    def action_go_back(self) -> None:
        self.app.pop_screen()
