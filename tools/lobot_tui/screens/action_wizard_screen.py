"""ActionWizardScreen: parameter input form before running a tool."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Select, SelectionList, Static
from textual.containers import Vertical, Horizontal

from ..actions.definitions import ActionDef, ActionField
from ..config import CONTROL_PLANE, TOOLS_LOCKED
import re as _re
from ..utils.tag_fetcher import fetch_dockerhub_tags, get_worker_nodes

# Sentinel used by Select when nothing is chosen
_NO_TAG = Select.BLANK


def _is_blank(value) -> bool:
    """Robustly detect a Select 'no selection' sentinel across Textual versions.
    Avoids 'is' identity checks, which can fail if the sentinel is not a true
    singleton in the installed Textual version."""
    if value is None:
        return True
    # The sentinel class is named _NoSelection (or similar) in all known versions
    return "selection" in type(value).__name__.lower()


class ActionWizardScreen(ModalScreen):
    """
    Shows input fields for an ActionDef.
    On confirm, dismisses with (argv: list, cwd: str, dry_run: bool).
    On cancel, dismisses with None.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
    ]

    def action_cancel(self) -> None:
        self.dismiss(None)

    def __init__(self, action: ActionDef) -> None:
        super().__init__()
        self._action = action
        self._locked = TOOLS_LOCKED
        # Pre-fetch nodes synchronously (kubectl is local, fast)
        has_node_field = any(
            f.field_type in ("node_exclude", "node_single")
            for f in action.fields
        )
        if has_node_field:
            # Workers only (for exclude lists — CP is auto-excluded by the scripts)
            self._worker_nodes = get_worker_nodes(CONTROL_PLANE, include_control_plane=False)
            # All nodes including CP (for single-target — user may need to update CP explicitly)
            self._all_nodes = get_worker_nodes(CONTROL_PLANE, include_control_plane=True)
        else:
            self._worker_nodes = []
            self._all_nodes = []

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Vertical(id="wizard-dialog"):
            yield Label(
                f"[bold cyan]{self._action.name}[/]",
                id="wizard-title",
                markup=True,
            )
            yield Label(self._action.description, classes="wizard-field-label")

            # Separate checkbox fields from other fields — checkboxes go on one row at the bottom
            checkbox_fields = [f for f in self._action.fields if f.field_type == "checkbox"]
            other_fields = [f for f in self._action.fields if f.field_type != "checkbox"]

            for f in other_fields:
                if f.field_type == "tag_select":
                    yield from self._compose_tag_select(f)
                elif f.field_type == "node_exclude":
                    yield from self._compose_node_exclude(f)
                elif f.field_type == "node_single":
                    yield from self._compose_node_single(f)
                else:
                    yield Label(f.label + (" *" if f.required else ""),
                                classes="wizard-field-label")
                    yield Input(
                        value=f.default,
                        placeholder=f.placeholder or f.default,
                        id=f"field-{f.name}",
                        classes="wizard-input",
                    )

            # All checkboxes (field checkboxes + dry-run) on a single horizontal row
            has_dry_run = self._action.has_dry_run
            if checkbox_fields or has_dry_run:
                with Horizontal(classes="wizard-checkbox-row"):
                    for f in checkbox_fields:
                        yield Checkbox(
                            f.label,
                            value=(f.default.lower() == "true"),
                            id=f"field-{f.name}",
                            classes="wizard-checkbox",
                        )
                    if has_dry_run:
                        yield Checkbox("Dry run", value=True,
                                       id="cb-dry-run", classes="wizard-checkbox")

            if self._locked:
                yield Label(
                    "[bold yellow]⚠ Tools locked — dry run only[/]",
                    classes="wizard-field-label",
                    markup=True,
                )

            with Horizontal(id="wizard-buttons"):
                yield Button("Cancel", variant="default", id="btn-cancel")
                if not self._locked:
                    yield Button("Run  (↵)", variant="error", id="btn-run")

    def _compose_tag_select(self, f: ActionField):
        """Yield label + image-name input + tag Select for a tag_select field."""
        yield Label(f.label + (" *" if f.required else ""), classes="wizard-field-label")
        yield Input(
            value=f.default,
            placeholder=f.placeholder or f.default,
            id=f"field-{f.name}-repo",
            classes="wizard-input",
        )
        yield Label("Tag (loading…)", id=f"lbl-{f.name}-tag", classes="wizard-field-label")
        yield Select(
            [],
            prompt="Loading tags…",
            id=f"field-{f.name}-tag",
            classes="wizard-select",
            allow_blank=True,
        )

    def _compose_node_exclude(self, f: ActionField):
        """Yield label + SelectionList (multi-check) for the -e exclude field."""
        yield Label(
            f"{f.label} (control plane always excluded)",
            classes="wizard-field-label",
        )
        if self._worker_nodes:
            items = [(node, node, False) for node in self._worker_nodes]
            yield SelectionList(*items, id=f"field-{f.name}", classes="wizard-selection-list")
        else:
            yield Static(
                "[dim]No worker nodes found via kubectl[/]",
                id=f"field-{f.name}",
                classes="wizard-field-label",
                markup=True,
            )

    def _compose_node_single(self, f: ActionField):
        """Yield label + Select (single) for the -n node field.
        Includes the control plane so the user can explicitly target it."""
        yield Label(f"{f.label} (leave blank for all nodes)", classes="wizard-field-label")
        if self._all_nodes:
            # First option has value "" so _collect_values gets a plain empty string —
            # avoids relying on Select.BLANK sentinel comparisons entirely.
            options = [("All nodes (default)", "")] + [(node, node) for node in self._all_nodes]
            yield Select(
                options,
                id=f"field-{f.name}",
                classes="wizard-select",
            )
        else:
            yield Static(
                "[dim]No nodes found via kubectl[/]",
                id=f"field-{f.name}",
                classes="wizard-field-label",
                markup=True,
            )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        """Start async tag loading after the screen is mounted."""
        for f in self._action.fields:
            if f.field_type == "tag_select":
                self.run_worker(
                    self._load_tags(f),
                    exclusive=False,
                    name=f"load-tags-{f.name}",
                )

    async def _load_tags(self, f: ActionField) -> None:
        """Fetch tags and populate the Select widget."""
        select_id = f"field-{f.name}-tag"
        label_id = f"lbl-{f.name}-tag"
        try:
            select = self.query_one(f"#{select_id}", Select)
        except Exception:
            return
        try:
            # Both image-pull and image-cleanup use DockerHub tags for the repo
            try:
                repo_input = self.query_one(f"#field-{f.name}-repo", Input)
                repo = repo_input.value.strip() or f.default
            except Exception:
                repo = f.default
            tags = await self._run_in_executor(fetch_dockerhub_tags, repo)
            # Sort by trailing YYYYMMDD(-N)? date code, newest first
            def _date_key(tag: str) -> str:
                m = _re.search(r'(\d{8})(?:-\d+)?$', tag)
                return m.group(1) if m else tag
            tags.sort(key=_date_key, reverse=True)
            def _label(tag: str, max_len: int = 80) -> str:
                if len(tag) <= max_len:
                    return tag
                return "…" + tag[-(max_len - 1):]
            options = [(_label(t), t) for t in tags]

            select.set_options(options)
            new_prompt = "Select a tag…" if options else "No tags found"
            select.prompt = new_prompt
            # For actions without use_latest (e.g. image-cleanup), pre-select the
            # first (newest) tag so the user doesn't have to make a selection.
            has_use_latest = any(f.name == "use_latest" for f in self._action.fields)
            if options and not has_use_latest:
                select.value = options[0][1]
            try:
                lbl = self.query_one(f"#{label_id}", Label)
                lbl.update("Tag")
            except Exception:
                pass
        except Exception as exc:
            select.prompt = f"Error loading tags: {exc}"

    async def _run_in_executor(self, fn, *args):
        """Run a blocking function in a thread pool and return the result."""
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, fn, *args)

    # ── Reactive: use_latest ↔ tag Select ────────────────────────────────────

    def on_select_changed(self, event: Select.Changed) -> None:
        """When a tag is selected, uncheck use_latest (which also re-enables the Select)."""
        # Only react to tag selects, not node selects
        if not (event.select.id and event.select.id.endswith("-tag")):
            return
        if event.value is _NO_TAG:
            return
        try:
            cb = self.query_one("#field-use_latest", Checkbox)
            cb.value = False
        except Exception:
            pass

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Enable/disable the tag Select based on use_latest state.
        Checked → Select disabled (grayed out, value ignored).
        Unchecked → Select re-enabled."""
        if event.checkbox.id != "field-use_latest":
            return
        for f in self._action.fields:
            if f.field_type == "tag_select":
                try:
                    sel = self.query_one(f"#field-{f.name}-tag", Select)
                    sel.disabled = event.value
                except Exception:
                    pass

    # ── Button handling ───────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "btn-cancel":
            self.dismiss(None)
        elif btn_id == "btn-run":
            self._do_run()

    # ── Value collection & submission ─────────────────────────────────────────

    def _collect_values(self, dry_run: bool) -> dict:
        values = {}
        for f in self._action.fields:
            if f.field_type == "tag_select":
                try:
                    repo_inp = self.query_one(f"#field-{f.name}-repo", Input)
                    repo = repo_inp.value.strip()
                except Exception:
                    repo = f.default
                # If use_latest is checked, ignore whatever tag is shown in the Select
                use_latest_active = False
                try:
                    use_latest_active = self.query_one("#field-use_latest", Checkbox).value
                except Exception:
                    pass
                try:
                    sel = self.query_one(f"#field-{f.name}-tag", Select)
                    tag_val = sel.value
                except Exception:
                    tag_val = _NO_TAG

                tag_blank = _is_blank(tag_val) or not tag_val
                if use_latest_active or tag_blank:
                    values[f.name] = repo  # command builder appends --latest when active
                elif self._action.name == "image-cleanup" and ":" in str(tag_val):
                    values[f.name] = str(tag_val)  # full image:tag already in value
                else:
                    values[f.name] = f"{repo}:{tag_val}"

            elif f.field_type == "node_exclude":
                try:
                    sel = self.query_one(f"#field-{f.name}", SelectionList)
                    values[f.name] = ",".join(str(v) for v in sel.selected)
                except Exception:
                    values[f.name] = ""

            elif f.field_type == "node_single":
                try:
                    sel = self.query_one(f"#field-{f.name}", Select)
                    v = sel.value
                    # Value is "" for "All nodes (default)" or a node name string;
                    # also guard against any BLANK sentinel leaking through.
                    values[f.name] = "" if (_is_blank(v) or str(v) == "") else str(v)
                except Exception:
                    values[f.name] = ""

            elif f.field_type == "checkbox":
                try:
                    cb = self.query_one(f"#field-{f.name}", Checkbox)
                    values[f.name] = cb.value
                except Exception:
                    values[f.name] = f.default.lower() == "true"

            else:
                try:
                    inp = self.query_one(f"#field-{f.name}", Input)
                    values[f.name] = inp.value.strip()
                except Exception:
                    values[f.name] = f.default

        values["dry_run"] = dry_run
        return values

    def _do_run(self) -> None:
        dry_run = False
        if self._action.has_dry_run:
            try:
                cb = self.query_one("#cb-dry-run", Checkbox)
                dry_run = cb.value
            except Exception:
                pass

        values = self._collect_values(dry_run=dry_run)

        # Validate required fields (only text inputs and tag_select have required)
        for f in self._action.fields:
            if f.required and f.field_type in ("input", "tag_select"):
                val = values.get(f.name, "")
                if not val:
                    try:
                        if f.field_type == "tag_select":
                            inp = self.query_one(f"#field-{f.name}-repo", Input)
                        else:
                            inp = self.query_one(f"#field-{f.name}", Input)
                        inp.focus()
                    except Exception:
                        pass
                    return

        argv = self._action.build_command(values)
        self.dismiss((argv, self._action.working_dir, dry_run))

    def on_key(self, event) -> None:
        if event.key == "enter" and not isinstance(self.focused, Input):
            self._do_run()
