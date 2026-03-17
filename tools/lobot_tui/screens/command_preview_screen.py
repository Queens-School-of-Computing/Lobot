"""CommandPreviewScreen: show exact command before running a destructive operation."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class CommandPreviewScreen(ModalScreen[bool]):
    """
    Shows the exact command that will be run and asks for explicit confirmation.
    Dismisses with True (run) or False (cancel).
    """

    def __init__(self, title: str, warning: str, argv: list) -> None:
        super().__init__()
        self._title = title
        self._warning = warning
        self._argv = argv
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
            yield Label(
                "[dim]Review carefully before confirming.[/]",
                id="preview-hint",
                markup=True,
            )
            with Horizontal(id="preview-buttons"):
                yield Button("Cancel", variant="default", id="btn-cancel")
                yield Button("Run  (↵)", variant="error", id="btn-run")

    def _run(self) -> None:
        if self._confirmed:
            return
        self._confirmed = True
        self.dismiss(True)

    def _cancel(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-run":
            self._run()
        else:
            self._cancel()

    def on_key(self, event) -> None:
        if event.key == "enter":
            self._run()
        elif event.key == "escape":
            self._cancel()
