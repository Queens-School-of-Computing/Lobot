"""ConfigViewerScreen: review the live config.yaml / config-env.yaml written by apply-config."""

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Label, LoadingIndicator, Markdown, MarkdownViewer

from ..config import HELM_CONFIG_ENV_LIVE, HELM_CONFIG_LIVE
from ..widgets.tricolour_stripe import TricolourStripe

_FILES = [
    ("config.yaml", Path(HELM_CONFIG_LIVE)),
    ("config-env.yaml", Path(HELM_CONFIG_ENV_LIVE)),
]


class ConfigViewerScreen(Screen):
    """Full-screen viewer for the live Helm config files output by apply-config.sh."""

    BINDINGS = [
        Binding("escape", "go_back", "Back", priority=True),
        Binding("q", "go_back", "Back", priority=True),
        Binding("1", "show_file_0", "config.yaml", show=True),
        Binding("2", "show_file_1", "config-env.yaml", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._active = 0  # index into _FILES

    def compose(self) -> ComposeResult:
        with Horizontal(id="screen-header"):
            yield Label("", id="screen-header-main", markup=True)
            yield Label("", id="top-bar-cat", markup=False)
        yield TricolourStripe("▄")
        yield LoadingIndicator(id="config-loading")

    def on_mount(self) -> None:
        self._refresh_header()
        self.call_after_refresh(lambda: self.run_worker(self._load()))

    def _refresh_header(self) -> None:
        name, path = _FILES[self._active]
        other_idx = 1 - self._active
        other_name = _FILES[other_idx][0]
        other_key = other_idx + 1
        self.query_one("#screen-header-main", Label).update(
            f" [bold cyan]CONFIG[/]  [bold]{name}[/]  {path}"
            f"  [dim][Esc/q] back  [{other_key}] switch to {other_name}[/]"
        )

    async def _load(self) -> None:
        name, path = _FILES[self._active]
        try:
            raw = path.read_text(encoding="utf-8")
            text = f"```yaml\n{raw}\n```"
        except OSError as exc:
            text = f"# Error\n\nCould not load `{path}`:\n\n```\n{exc}\n```"
        loading = self.query_one("#config-loading")
        loading.display = False
        # Remove any existing viewer before mounting a new one
        for old in self.query("#config-viewer"):
            await old.remove()
        await self.mount(MarkdownViewer(text, id="config-viewer", show_table_of_contents=False))
        try:
            self.query_one("#config-viewer").query_one(Markdown).focus()
        except Exception:
            self.query_one("#config-viewer").focus()

    async def _switch_to(self, idx: int) -> None:
        if idx == self._active:
            return
        self._active = idx
        self._refresh_header()
        loading = self.query_one("#config-loading")
        loading.display = True
        await self._load()

    def action_show_file_0(self) -> None:
        self.run_worker(self._switch_to(0))

    def action_show_file_1(self) -> None:
        self.run_worker(self._switch_to(1))

    def action_go_back(self) -> None:
        self.app.pop_screen()
