"""ClusterSummaryWidget: per-lab resource bars."""

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from ..data.collector import ClusterStateUpdated
from ..data.models import ClusterState, LabSummary

# Friendly display names for known labs
LAB_DISPLAY_NAMES = {
    "lobot_a40": "Lobot [A40]",
    "lobot_a16": "Lobot [A16]",
    "lobot_a5000": "Lobot [A5000]",
    "lobot_problackwell": "Lobot [Blackwell]",
    "gandslab": "GOAL&SWIMS",
    "edemsmithbusiness": "Smith Business",
    "miblab": "MIB Lab",
    "mulab": "MU Lab",
    "bamlab": "BAM Lab",
    "riselab": "RISE Lab",
    "caslab": "CAS Lab",
    "digilab": "DIGI Lab",
    "devlab": "Dev Lab",
    "winemocollab": "WineMotion",
}

BAR_WIDTH = 12


def _bar(used: int, total: int, width: int = BAR_WIDTH) -> str:
    """Return a progress bar string."""
    if total <= 0:
        return "░" * width
    ratio = min(used / total, 1.0)
    filled = round(ratio * width)
    return "█" * filled + "░" * (width - filled)


def _bar_color(used: int, total: int) -> str:
    """Return color class based on utilisation."""
    if total <= 0:
        return "bar-full"
    ratio = used / total
    if ratio >= 0.90:
        return "bar-crit"
    elif ratio >= 0.75:
        return "bar-warn"
    return "bar-full"


def _render_lab(lab: LabSummary) -> str:
    """Render a single lab as a Rich markup string."""
    display = LAB_DISPLAY_NAMES.get(lab.name, lab.name)
    lines = []

    # Lab name header
    lines.append(f"[bold cyan]{display}[/]  [{lab.pod_count} pod{'s' if lab.pod_count != 1 else ''}]")

    # CPU row
    cpu_used = lab.cpu_used
    cpu_bar = _bar(cpu_used, lab.cpu_total)
    cpu_color = _bar_color(cpu_used, lab.cpu_total)
    lines.append(
        f"  [dim]CPU[/] [{cpu_color}]{cpu_bar}[/] "
        f"[dim]{cpu_used}/{lab.cpu_total}[/]"
    )

    # RAM row
    ram_used = lab.ram_used_gb
    ram_bar = _bar(ram_used, lab.ram_total_gb)
    ram_color = _bar_color(ram_used, lab.ram_total_gb)
    lines.append(
        f"  [dim]RAM[/] [{ram_color}]{ram_bar}[/] "
        f"[dim]{ram_used}/{lab.ram_total_gb}GB[/]"
    )

    # GPU row (only if lab has GPUs)
    if lab.has_gpu:
        gpu_used = lab.gpu_used
        gpu_bar = _bar(gpu_used, lab.gpu_total)
        gpu_color = _bar_color(gpu_used, lab.gpu_total)
        lines.append(
            f"  [dim]GPU[/] [{gpu_color}]{gpu_bar}[/] "
            f"[dim]{gpu_used}/{lab.gpu_total}[/]"
        )

    return "\n".join(lines)


class ClusterSummaryWidget(Widget):
    """Displays per-lab resource utilisation bars."""

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

        # Sort labs: lobot_* first, then alphabetical
        def sort_key(name: str) -> tuple:
            return (0 if name.startswith("lobot_") else 1, name)

        lab_blocks = []
        for name in sorted(state.labs.keys(), key=sort_key):
            lab_blocks.append(_render_lab(state.labs[name]))

        content.update("\n\n".join(lab_blocks))
