"""MainScreen: primary btop-style dashboard layout."""

import asyncio
import json
import socket
from datetime import datetime
from pathlib import Path
from typing import Callable

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Input, Label, Static

from ..config import CONTROL_PLANE, IS_DEV, JUPYTERHUB_NAMESPACE, NS_FILTERS_FILE, TOOLS_DIR, TOOLS_LOCKED
from ..data.collector import ClusterStateUpdated, DataCollector
from ..data.models import NodeInfo, PodInfo
from ..widgets.actions_panel import ActionsPanelWidget
from ..widgets.cluster_summary import ClusterSummaryWidget
from ..widgets.node_table import NodeTableWidget
from ..widgets.pod_table import PodTableWidget
from ..widgets.status_bar import StatusBarWidget
from .action_screen import ActionScreen
from .action_wizard_screen import ActionWizardScreen
from .announcement_screen import AnnouncementScreen
from .console_screen import ConsoleScreen
from .help_screen import HelpScreen
from .exec_screen import ExecScreen
from .logs_screen import LogsScreen
from .pod_detail_screen import PodDetailScreen
from ..actions.definitions import ACTIONS_BY_KEY


_NAMESPACES_DEFAULT = [JUPYTERHUB_NAMESPACE, "all"]

# Default pre-filled filters per namespace (used when no saved value exists)
_DEFAULT_NS_FILTERS: dict[str, str] = {
    JUPYTERHUB_NAMESPACE: "jupyter|jhub",
}


def _load_ns_filters() -> dict[str, str]:
    """Load saved per-namespace filters, merging with defaults."""
    result = dict(_DEFAULT_NS_FILTERS)
    try:
        if NS_FILTERS_FILE.exists():
            data = json.loads(NS_FILTERS_FILE.read_text())
            if isinstance(data, dict):
                result.update(data)
    except Exception:
        pass
    return result


def _save_ns_filters(filters: dict[str, str]) -> None:
    try:
        NS_FILTERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        NS_FILTERS_FILE.write_text(json.dumps(filters))
    except Exception:
        pass


async def _fetch_namespaces() -> list[str]:
    """Return sorted namespace list from kubectl, falling back to defaults."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "kubectl", "get", "namespaces",
            "-o", "jsonpath={range .items[*]}{.metadata.name}{'\\n'}{end}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        names = [n.strip() for n in stdout.decode().splitlines() if n.strip()]
        if names:
            ordered = [JUPYTERHUB_NAMESPACE] if JUPYTERHUB_NAMESPACE in names else []
            ordered += sorted(n for n in names if n != JUPYTERHUB_NAMESPACE)
            ordered.append("all")
            return ordered
    except Exception:
        pass
    return _NAMESPACES_DEFAULT


class MainScreen(Screen):
    """The primary dashboard screen."""

    BINDINGS = [
        ("q", "quit_app", "Quit"),
        ("r", "force_refresh", "Refresh"),
        ("question_mark", "show_help", "Help"),
        ("grave_accent", "show_console", "Console"),
        ("1", "tool_1", "image-pull"),
        ("2", "tool_2", "image-cleanup"),
        ("3", "tool_3", "apply-config"),
        ("4", "tool_4", "sync-groups"),
        ("5", "tool_5", "helm upgrade"),
        ("6", "tool_6", "announcement"),
        # Pod actions
        ("l", "pod_logs", "Logs"),
        ("x", "pod_exec", "Exec"),
        ("X", "pod_delete", "Delete pod"),
        ("d", "pod_describe", "Describe pod"),
        ("enter", "pod_describe", "Describe pod"),
        ("slash", "focus_filter", "Filter"),
        ("escape", "clear_filter", "Clear filter"),
        ("n", "cycle_namespace", "Namespace"),
        # Node actions
        ("c", "node_cordon", "Cordon"),
        ("u", "node_uncordon", "Uncordon"),
        ("w", "node_drain", "Drain"),
    ]

    def __init__(self, collector: DataCollector) -> None:
        super().__init__()
        self._collector = collector
        self._ns_idx = 0
        self._filter_active = False
        self._namespaces: list[str] = _NAMESPACES_DEFAULT
        self._pending_key: str | None = None
        self._pending_timer = None
        self._ns_filters: dict[str, str] = _load_ns_filters()

    def compose(self) -> ComposeResult:
        hostname = socket.gethostname()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        yield Label(
            f" [bold cyan]LOBOT[/]  {hostname}  {'[bold yellow]DEV[/]' if IS_DEV else '[bold green]PROD[/]'}  [dim]{now}[/]",
            id="top-bar",
            markup=True,
        )
        with Horizontal(id="top-section"):
            with Vertical(id="summary-panel"):
                yield ClusterSummaryWidget(id="cluster-summary")
            with Vertical(id="nodes-panel"):
                yield NodeTableWidget(id="node-table")
        with Vertical(id="pods-panel"):
            with Horizontal(id="pod-filter-bar"):
                yield Label(
                    f"[bold]PODS[/]  ns:[cyan]{self._namespaces[self._ns_idx]}[/]  filter:",
                    id="pod-filter-label",
                    markup=True,
                )
                initial_filter = self._ns_filters.get(self._namespaces[self._ns_idx], "")
                yield Input(value=initial_filter, placeholder="type to filter…", id="pod-filter-input")
                yield Static("", id="pod-count-outer", markup=True)
            yield PodTableWidget(id="pod-table")
        yield ActionsPanelWidget(id="actions-panel")
        yield StatusBarWidget(id="status-bar")

    def on_mount(self) -> None:
        self.set_interval(1, self._tick_clock)
        self.query_one("#pod-table").focus()
        asyncio.ensure_future(self._load_namespaces())
        # Apply initial filter to pod table
        initial_filter = self._ns_filters.get(self._namespaces[self._ns_idx], "")
        if initial_filter:
            self.query_one("#pod-table", PodTableWidget).filter_text = initial_filter

    async def _load_namespaces(self) -> None:
        self._namespaces = await _fetch_namespaces()

    def _tick_clock(self) -> None:
        hostname = socket.gethostname()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.query_one("#top-bar", Label).update(
                f" [bold cyan]LOBOT[/]  {hostname}  {'[bold yellow]DEV[/]' if IS_DEV else '[bold green]PROD[/]'}  [dim]{now}[/]"
            )
        except Exception:
            pass

    # ── Double-keypress confirmation ───────────────────────────────────────

    def _require_confirm(self, key: str, description: str, action_fn: Callable) -> None:
        """Prime on first press; execute on second press within 2 seconds."""
        if self._pending_key == key:
            self._clear_pending()
            action_fn()
        else:
            self._pending_key = key
            if self._pending_timer is not None:
                self._pending_timer.stop()
            self._pending_timer = self.set_timer(2.0, self._clear_pending)
            self.notify(f"Press [{key}] again to confirm: {description}", timeout=2.0)

    def _clear_pending(self) -> None:
        self._pending_key = None
        self._pending_timer = None

    # ── ClusterStateUpdated ────────────────────────────────────────────────

    def on_cluster_state_updated(self, event: ClusterStateUpdated) -> None:
        for widget_id in ["cluster-summary", "node-table", "pod-table", "status-bar"]:
            try:
                self.query_one(f"#{widget_id}").post_message(event)
            except Exception:
                pass

    # ── Pod filter input ──────────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "pod-filter-input":
            pod_table = self.query_one("#pod-table", PodTableWidget)
            pod_table.filter_text = event.value
            # Persist filter for current namespace
            ns = self._namespaces[self._ns_idx]
            self._ns_filters[ns] = event.value
            _save_ns_filters(self._ns_filters)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "pod-filter-input":
            self.query_one("#pod-datatable").focus()

    # ── Helpers ───────────────────────────────────────────────────────────

    def _selected_pod(self) -> "PodInfo | None":
        try:
            return self.query_one("#pod-table", PodTableWidget).selected_pod
        except Exception:
            return None

    def _selected_node(self) -> "NodeInfo | None":
        try:
            return self.query_one("#node-table", NodeTableWidget).selected_node
        except Exception:
            return None

    # ── Global actions ────────────────────────────────────────────────────

    def action_quit_app(self) -> None:
        self._require_confirm("q", "quit lobot-tui", lambda: self.app.exit())

    def action_force_refresh(self) -> None:
        asyncio.ensure_future(self._collector.force_refresh())

    def action_show_help(self) -> None:
        self.app.push_screen(HelpScreen())

    def action_show_console(self) -> None:
        self.app.push_screen(ConsoleScreen())

    def action_focus_filter(self) -> None:
        inp = self.query_one("#pod-filter-input", Input)
        inp.focus()

    def action_clear_filter(self) -> None:
        inp = self.query_one("#pod-filter-input", Input)
        inp.value = ""
        self.query_one("#pod-datatable").focus()

    def action_cycle_namespace(self) -> None:
        # Save current namespace's filter before switching
        old_ns = self._namespaces[self._ns_idx]
        inp = self.query_one("#pod-filter-input", Input)
        self._ns_filters[old_ns] = inp.value
        _save_ns_filters(self._ns_filters)

        self._ns_idx = (self._ns_idx + 1) % len(self._namespaces)
        ns = self._namespaces[self._ns_idx]
        self._collector.namespace = ns
        try:
            self.query_one("#pod-filter-label", Label).update(
                f"[bold]PODS[/]  ns:[cyan]{ns}[/]  filter:"
            )
        except Exception:
            pass

        # Restore saved filter for the new namespace (setting inp.value triggers on_input_changed)
        inp.value = self._ns_filters.get(ns, "")
        asyncio.ensure_future(self._collector.force_refresh())

    # ── Pod actions ───────────────────────────────────────────────────────

    def action_pod_logs(self) -> None:
        pod = self._selected_pod()
        if pod:
            self.app.push_screen(LogsScreen(pod))

    def action_pod_describe(self) -> None:
        pod = self._selected_pod()
        if pod:
            self.app.push_screen(PodDetailScreen(pod))

    def action_pod_exec(self) -> None:
        pod = self._selected_pod()
        if pod:
            self.app.push_screen(ExecScreen(pod))

    def action_pod_delete(self) -> None:
        pod = self._selected_pod()
        if not pod:
            return
        argv = ["kubectl", "delete", "pod", pod.name, "-n", pod.namespace]
        self._require_confirm(
            "X", f"delete pod {pod.name}",
            lambda: self.app.push_screen(ActionScreen("delete-pod", argv, auto_close=True)),
        )

    # ── Node actions ──────────────────────────────────────────────────────

    def action_node_cordon(self) -> None:
        node = self._selected_node()
        if not node or node.is_control_plane:
            return
        self._require_confirm(
            "c", f"cordon {node.name}",
            lambda: self.app.push_screen(ActionScreen("cordon", ["kubectl", "cordon", node.name], auto_close=True)),
        )

    def action_node_uncordon(self) -> None:
        node = self._selected_node()
        if not node or node.is_control_plane:
            return
        self._require_confirm(
            "u", f"uncordon {node.name}",
            lambda: self.app.push_screen(ActionScreen("uncordon", ["kubectl", "uncordon", node.name], auto_close=True)),
        )

    def action_node_drain(self) -> None:
        node = self._selected_node()
        if not node or node.is_control_plane:
            return
        argv = ["kubectl", "drain", node.name, "--ignore-daemonsets", "--delete-emptydir-data"]
        self._require_confirm(
            "w", f"DRAIN {node.name} — evicts all pods!",
            lambda: self.app.push_screen(ActionScreen("drain", argv, auto_close=True)),
        )

    # ── Tool actions (1–6) ────────────────────────────────────────────────

    def _do_tool(self, key: str) -> None:
        action = ACTIONS_BY_KEY.get(key)
        if not action:
            return

        if TOOLS_LOCKED and not action.has_dry_run:
            self.notify(
                f"[bold yellow]Tools locked[/] — {action.name} has no dry-run mode and cannot run.",
                title="Dry run only",
                timeout=4.0,
            )
            return

        if action.fields or action.has_dry_run:
            self.app.push_screen(
                ActionWizardScreen(action),
                callback=lambda result: self._on_wizard_result(result, action),
            )
        else:
            self._launch_tool(action, action.build_command({}), action.working_dir)

    def _launch_tool(self, action, argv, cwd) -> None:
        self.app.push_screen(ActionScreen(action.name, argv, cwd=cwd))

    def _on_wizard_result(self, result, action) -> None:
        if result is None:
            return
        argv, cwd, dry_run = result
        if not argv:
            return
        self.app.push_screen(ActionScreen(action.name, argv, cwd=cwd))

    def action_tool_1(self) -> None:
        self._do_tool("1")

    def action_tool_2(self) -> None:
        self._do_tool("2")

    def action_tool_3(self) -> None:
        self._do_tool("3")

    def action_tool_4(self) -> None:
        self._do_tool("4")

    def action_tool_5(self) -> None:
        self._do_tool("5")

    def action_tool_6(self) -> None:
        self.app.push_screen(AnnouncementScreen())
