"""ConfirmScreen: generic modal for destructive actions."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class ConfirmScreen(ModalScreen[bool]):
    """
    Confirmation modal that dismisses with True (confirm) or False (cancel).

    Usage:
        def on_result(confirmed: bool) -> None:
            if confirmed:
                self.app.push_screen(ActionScreen(...))
        self.app.push_screen(ConfirmScreen(title, message), on_result)

    The on_result callback is scheduled via call_next on the calling screen's
    message pump (Textual's built-in dismiss mechanism), which runs cleanly
    after ConfirmScreen is fully removed from the stack.
    """

    def __init__(self, title: str, message: str) -> None:
        super().__init__()
        self._title = title
        self._message = message
        self._confirmed = False

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label(f"⚠  {self._title}", id="confirm-title", markup=True)
            yield Label(self._message, id="confirm-message")
            with Horizontal(id="confirm-buttons"):
                yield Button("Cancel  (Esc)", variant="default", id="btn-cancel")
                yield Button("Confirm  (Enter/y)", variant="error", id="btn-confirm")

    def _confirm(self) -> None:
        if self._confirmed:  # guard: Enter on focused button can double-fire
            return
        self._confirmed = True
        self.dismiss(True)

    def _cancel(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-confirm":
            self._confirm()
        else:
            self._cancel()

    def on_key(self, event) -> None:
        if event.key in ("y", "enter"):
            self._confirm()
        elif event.key == "escape":
            self._cancel()
