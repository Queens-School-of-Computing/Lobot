"""NodePickerScreen: modal for selecting cluster nodes via checkboxes."""

import subprocess

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Label, Static
from textual.containers import Vertical, Horizontal, ScrollableContainer

from ..config import CONTROL_PLANE


def _get_nodes() -> list:
    """Return list of all node names from kubectl, sorted."""
    try:
        result = subprocess.run(
            ["kubectl", "get", "nodes", "--no-headers",
             "-o", "custom-columns=NAME:.metadata.name"],
            capture_output=True, text=True, timeout=10,
        )
        return sorted(n.strip() for n in result.stdout.splitlines() if n.strip())
    except Exception:
        return []


class NodePickerScreen(ModalScreen):
    """
    List all cluster nodes as checkboxes.

    multi=True  → multi-select; returns comma-separated string (for -e exclude).
    multi=False → single-select; returns one node name (for -n node).

    Dismisses with the resulting string, or None on cancel.
    """

    def __init__(self, multi: bool = True) -> None:
        super().__init__()
        self._multi = multi
        self._nodes = _get_nodes()

    def compose(self) -> ComposeResult:
        title = "Select nodes to exclude" if self._multi else "Select a single target node"
        with Vertical(id="node-picker-dialog"):
            yield Label(f"[bold cyan]{title}[/]", id="node-picker-title", markup=True)
            if not self._nodes:
                yield Static("[yellow]No nodes found (kubectl unavailable?)[/]", markup=True)
            else:
                with ScrollableContainer(id="node-picker-list"):
                    for node in self._nodes:
                        if self._multi:
                            # Pre-check and disable the control plane
                            is_cp = node == CONTROL_PLANE
                            yield Checkbox(
                                node,
                                value=is_cp,
                                id=f"node-cb-{node}",
                                disabled=is_cp,
                            )
                        else:
                            # For single-node selection, skip the control plane entirely
                            if node != CONTROL_PLANE:
                                yield Checkbox(node, value=False, id=f"node-cb-{node}")

            with Horizontal(id="node-picker-buttons"):
                yield Button("Cancel", variant="default", id="btn-np-cancel")
                yield Button("OK", variant="primary", id="btn-np-ok")

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if not self._multi and event.value:
            # Single-select: uncheck all other nodes
            for node in self._nodes:
                if node == CONTROL_PLANE:
                    continue
                cb_id = f"node-cb-{node}"
                if cb_id != event.checkbox.id:
                    try:
                        cb = self.query_one(f"#{cb_id}", Checkbox)
                        cb.value = False
                    except Exception:
                        pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-np-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-np-ok":
            selected = []
            for node in self._nodes:
                if self._multi and node == CONTROL_PLANE:
                    # Always include the pre-checked control plane in exclude list
                    selected.append(node)
                    continue
                if node == CONTROL_PLANE:
                    continue
                try:
                    cb = self.query_one(f"#node-cb-{node}", Checkbox)
                    if cb.value:
                        selected.append(node)
                except Exception:
                    pass
            self.dismiss(",".join(selected))

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
