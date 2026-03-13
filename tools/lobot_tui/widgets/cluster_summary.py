"""ClusterSummaryWidget: per-lab resource table."""

from rich.markup import escape as markup_escape
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from ..data.collector import ClusterStateUpdated
from ..data.models import ClusterState, LabSummary

_LAB_W = 14   # max lab name display width
_CPU_W = 7    # "142/256"
_RAM_W = 9    # "704/1007G"
_GPU_W = 5    # "  5/8 " or "  –  "


def _util_color(used: int, total: int) -> str:
    if total <= 0:
        return "dim"
    ratio = used / total
    if ratio >= 0.90:
        return "red"
    elif ratio >= 0.75:
        return "yellow"
    return "green"


def _render_table(labs: dict) -> str:
    def sort_key(name: str) -> tuple:
        return (0 if name.startswith("lobot_") else 1, name)

    sorted_labs = sorted(labs.values(), key=lambda l: sort_key(l.name))

    header = (
        f"[bold dim]{'LAB':<{_LAB_W}}  {'#':>2}  "
        f"{'CPU':>{_CPU_W}}  {'RAM':>{_RAM_W}}  {'GPU':>{_GPU_W}}[/]"
    )
    lines = [header]

    for lab in sorted_labs:
        name = markup_escape(lab.name[:_LAB_W])

        pods_str = f"{lab.pod_count:>2}"

        cpu_c = _util_color(lab.cpu_used, lab.cpu_total)
        cpu_str = f"{lab.cpu_used}/{lab.cpu_total}"

        ram_c = _util_color(lab.ram_used_gb, lab.ram_total_gb)
        ram_str = f"{lab.ram_used_gb}/{lab.ram_total_gb}G"

        if lab.has_gpu:
            gpu_c = _util_color(lab.gpu_used, lab.gpu_total)
            gpu_str = f"{lab.gpu_used}/{lab.gpu_total}"
        else:
            gpu_c = "dim"
            gpu_str = "–"

        row = (
            f"[cyan]{name:<{_LAB_W}}[/]  [dim]{pods_str}[/]"
            f"  [{cpu_c}]{cpu_str:>{_CPU_W}}[/]"
            f"  [{ram_c}]{ram_str:>{_RAM_W}}[/]"
            f"  [{gpu_c}]{gpu_str:>{_GPU_W}}[/]"
        )
        lines.append(row)

    return "\n".join(lines)


class ClusterSummaryWidget(Widget):
    """Displays per-lab resource utilisation as a compact table."""

    DEFAULT_CSS = ""

    def compose(self) -> ComposeResult:
        yield Static("Loading cluster data…", id="summary-content")

    def on_cluster_state_updated(self, event: ClusterStateUpdated) -> None:
        self._refresh_display(event.state)

    def _refresh_display(self, state: ClusterState) -> None:
        content = self.query_one("#summary-content", Static)

        if not state.labs:
            if state.alloc_error:
                content.update(f"[red]Error: {state.alloc_error}[/]")
            else:
                content.update("[dim]Waiting for allocation data…[/]")
            return

        content.update(_render_table(state.labs))
