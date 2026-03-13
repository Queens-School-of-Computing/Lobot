"""ActionWizardScreen: parameter input form before running a tool."""

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Static
from textual.containers import Vertical, Horizontal

from ..actions.definitions import ActionDef


class ActionWizardScreen(ModalScreen):
    """
    Shows input fields for an ActionDef.
    On confirm, dismisses with (argv: list, cwd: str, dry_run: bool).
    On cancel, dismisses with None.
    """

    def __init__(self, action: ActionDef) -> None:
        super().__init__()
        self._action = action

    def compose(self) -> ComposeResult:
        with Vertical(id="wizard-dialog"):
            yield Label(
                f"[bold cyan]{self._action.name}[/]",
                id="wizard-title",
                markup=True,
            )
            yield Label(self._action.description, classes="wizard-field-label")

            # One Input per field
            for f in self._action.fields:
                yield Label(f.label + ("" if not f.required else " *"), classes="wizard-field-label")
                yield Input(
                    value=f.default,
                    placeholder=f.placeholder or f.default,
                    id=f"field-{f.name}",
                    classes="wizard-input",
                )

            # Dry-run checkbox if supported
            if self._action.has_dry_run:
                yield Checkbox("Dry run (safe preview — no changes made)", value=True,
                               id="cb-dry-run", classes="wizard-checkbox")

            with Horizontal(id="wizard-buttons"):
                yield Button("Cancel", variant="default", id="btn-cancel")
                if self._action.has_dry_run:
                    yield Button("Dry Run", variant="primary", id="btn-dry-run")
                yield Button("Run", variant="error", id="btn-run")

    def _collect_values(self, dry_run: bool) -> dict:
        values = {}
        for f in self._action.fields:
            inp = self.query_one(f"#field-{f.name}", Input)
            values[f.name] = inp.value.strip()
        values["dry_run"] = dry_run
        return values

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-dry-run":
            values = self._collect_values(dry_run=True)
            argv = self._action.build_command(values)
            self.dismiss((argv, self._action.working_dir, True))
        elif event.button.id == "btn-run":
            dry_run = False
            if self._action.has_dry_run:
                try:
                    cb = self.query_one("#cb-dry-run", Checkbox)
                    dry_run = cb.value
                except Exception:
                    pass
            values = self._collect_values(dry_run=dry_run)
            # Validate required fields
            for f in self._action.fields:
                if f.required and not values.get(f.name):
                    # Flash the empty input
                    try:
                        inp = self.query_one(f"#field-{f.name}", Input)
                        inp.focus()
                    except Exception:
                        pass
                    return
            argv = self._action.build_command(values)
            self.dismiss((argv, self._action.working_dir, dry_run))

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
