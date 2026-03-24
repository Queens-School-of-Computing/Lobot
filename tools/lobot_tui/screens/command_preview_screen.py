"""CommandPreviewScreen: show exact command before running a destructive operation."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class CommandPreviewScreen(ModalScreen[bool]):
    """
    Shows the exact command that will be run and asks for explicit confirmation.
    Dismisses with True (run) or False (cancel).

    Pass docs_path to show a "View Docs (d)" button that opens the file in the markdown viewer.
    """

    def __init__(self, title: str, warning: str, argv: list, docs_path: Path | None = None) -> None:
        super().__init__()
        self._title = title
        self._warning = warning
        self._argv = argv
        self._docs_path = docs_path
        self._confirmed = False

    def compose(self) -> ComposeResult:
        # Format the command with line-continuation breaks for readability
        cmd_parts = list(self._argv)
        if len(cmd_parts) > 4:
            # Break at flags (words starting with --) for display
            lines = []
            current = []
            for part in cmd_parts:
                if part.startswith("--") and current:
                    lines.append(" ".join(current) + " \\")
                    current = [part]
                else:
                    current.append(part)
            if current:
                lines.append(" ".join(current))
            cmd_display = "\n  ".join(lines)
        else:
            cmd_display = " ".join(cmd_parts)

        with Vertical(id="preview-dialog"):
            yield Label(
                f"[bold red]⚠  {self._title}[/]",
                id="preview-title",
                markup=True,
            )
            yield Label(self._warning, id="preview-warning")
            yield Label("Command that will run:", classes="preview-section-label")
            yield Static(cmd_display, id="preview-command")
            hint = "[dim]Review carefully before confirming.[/]"
            if self._docs_path:
                hint += "  Press [bold](d)[/] to read the documentation first."
            yield Label(hint, id="preview-hint", markup=True)
            with Horizontal(id="preview-buttons"):
                yield Button("Cancel  (q)", variant="error", id="btn-cancel")
                if self._docs_path:
                    yield Button("View Docs  (d)", variant="warning", id="btn-docs")
                yield Button("Run  (r)", variant="success", id="btn-run")

    def on_mount(self) -> None:
        self.query_one("#btn-cancel").focus()

    def _open_docs(self) -> None:
        from .guide_screen import GuideScreen
        self.app.push_screen(GuideScreen(path=self._docs_path, label="DOCS"))

    def _run(self) -> None:
        if self._confirmed:
            return
        self._confirmed = True
        self.dismiss(True)

    def _cancel(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-docs":
            self._open_docs()
        elif event.button.id == "btn-run":
            self._run()
        else:
            self._cancel()

    def on_key(self, event) -> None:
        if event.key in ("enter", "space") and isinstance(self.focused, Button):
            self.focused.press()
            event.stop()
        elif event.key == "r":
            self._run()
        elif event.key in ("escape", "q"):
            self._cancel()
        elif event.key == "d" and self._docs_path:
            self._open_docs()
