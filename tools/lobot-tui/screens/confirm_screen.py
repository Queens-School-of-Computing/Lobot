"""ConfirmScreen: generic modal for destructive actions."""

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static
from textual.containers import Vertical, Horizontal


class ConfirmScreen(ModalScreen[bool]):
    """
    Push this screen to ask the user to confirm a destructive action.
    Returns True if confirmed, False if cancelled.

    Usage:
        result = await self.app.push_screen_wait(ConfirmScreen(title, message))
    """

    def __init__(self, title: str, message: str) -> None:
        super().__init__()
        self._title = title
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label(f"⚠  {self._title}", id="confirm-title", markup=True)
            yield Label(self._message, id="confirm-message")
            with Horizontal(id="confirm-buttons"):
                yield Button("Cancel", variant="default", id="btn-cancel")
                yield Button("Confirm", variant="error", id="btn-confirm")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-confirm":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def on_key(self, event) -> None:
        if event.key == "y":
            self.dismiss(True)
        elif event.key in ("n", "escape"):
            self.dismiss(False)
