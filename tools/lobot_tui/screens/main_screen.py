"""MainScreen: primary btop-style dashboard layout."""

import asyncio
import json
import socket
from datetime import datetime
from typing import Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Input, Label, Static

from ..actions.definitions import ACTIONS_BY_KEY
from ..config import (
    IS_DEV,
    JUPYTERHUB_NAMESPACE,
    NS_FILTERS_FILE,
    TOOLS_LOCKED,
)
from ..data.collector import ClusterStateUpdated, ServiceCollector
from ..data.job_manager import JobCompleted
from ..data.models import NodeInfo, PodInfo
from ..widgets.actions_panel import ActionsPanelWidget, HintClicked
from ..widgets.cluster_summary import ResourceTableWidget
from ..widgets.node_table import NodeTableWidget
from ..widgets.pod_table import PodTableWidget
from ..widgets.status_bar import StatusBarWidget
from .action_screen import ActionScreen
from .action_wizard_screen import ActionWizardScreen
from .announcement_screen import AnnouncementScreen
from .command_preview_screen import CommandPreviewScreen
from .console_screen import ConsoleScreen
from .exec_screen import ExecScreen
from .help_screen import HelpScreen
from .jobs_screen import JobsScreen
from .logs_screen import LogsScreen
from .pod_detail_screen import PodDetailScreen

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
            "kubectl",
            "get",
            "namespaces",
            "-o",
            "jsonpath={range .items[*]}{.metadata.name}{'\\n'}{end}",
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
        ("R", "force_refresh", "Refresh"),
        ("question_mark", "show_help", "Help"),
        ("grave_accent", "show_console", "Console"),
        ("b", "show_jobs", "Jobs"),
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
        ("f", "focus_filter", "Filter"),
        Binding("tab", "cycle_panel", "Switch panel", priority=True, show=False),
        ("n", "toggle_node_filter", "Node filter"),
        ("r", "toggle_resource_filter", "Resource filter"),
        Binding("escape", "escape_focus", "", priority=True, show=False),
        ("N", "cycle_namespace", "Namespace"),
        # Node actions
        ("c", "node_cordon", "Cordon"),
        ("u", "node_uncordon", "Uncordon"),
        ("w", "node_drain", "Drain"),
    ]

    def __init__(self, collector: ServiceCollector) -> None:
        super().__init__()
        self._collector = collector
        self._ns_idx = 0
        self._filter_active = False
        self._namespaces: list[str] = _NAMESPACES_DEFAULT
        self._pending_key: str | None = None
        self._pending_timer = None
        self._ns_filters: dict[str, str] = _load_ns_filters()
        self._last_cluster_state = None

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
                yield ResourceTableWidget(id="resource-table")
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
                yield Input(
                    value=initial_filter, placeholder="type to filter…", id="pod-filter-input"
                )
                yield Static("", id="pod-count-outer", markup=True)
            yield PodTableWidget(id="pod-table")
        yield ActionsPanelWidget(id="actions-panel")
        yield StatusBarWidget(id="status-bar")

    def on_mount(self) -> None:
        self.set_interval(1, self._tick_clock)
        asyncio.ensure_future(self._load_namespaces())
        # Apply initial namespace and filter to pod table
        pod_table = self.query_one("#pod-table", PodTableWidget)
        pod_table.namespace = self._namespaces[self._ns_idx]
        initial_filter = self._ns_filters.get(self._namespaces[self._ns_idx], "")
        if initial_filter:
            pod_table.filter_text = initial_filter
        self._update_pod_label()

    async def _load_namespaces(self) -> None:
        self._namespaces = await _fetch_namespaces()

    def _tick_clock(self) -> None:
        hostname = socket.gethostname()
        now = datetime.now().strftime("%H:%M:%S")
        state = self._last_cluster_state

        if state:
            total_pods = sum(1 for p in state.pods if p.name.startswith("jupyter-"))
            total_nodes = sum(1 for n in state.nodes if not n.is_control_plane)
            ready_nodes = sum(
                1
                for n in state.nodes
                if not n.is_control_plane and n.status == "Ready" and n.schedulable
            )
            gpu_total = sum(r.gpu_total for r in state.resources.values())
            gpu_used = sum(r.gpu_used for r in state.resources.values())
            stats = (
                f"  [dim]│[/]  "
                f"[#79c0ff]Pods[/] [white]{total_pods}[/]  "
                f"[#79c0ff]Nodes[/] [white]{ready_nodes}/{total_nodes}[/]  "
                f"[#79c0ff]GPU[/] [white]{gpu_used}/{gpu_total}[/]"
            )
        else:
            stats = ""

        badge = "[bold yellow] DEV [/]" if IS_DEV else "[bold green] PROD [/]"
        try:
            self.query_one("#top-bar", Label).update(
                f" [bold #58a6ff]LOBOT[/]  [dim]{hostname}[/]  {badge}  [dim]{now}[/]{stats}"
            )
        except Exception:
            pass
        self._update_job_indicator()

    def _update_job_indicator(self) -> None:
        """Refresh the running-job status in the actions panel hint bar."""
        try:
            panel = self.query_one("#actions-panel", ActionsPanelWidget)
        except Exception:
            return
        job = self.app.job_manager.current_job
        if job is None or job.status != "running":
            return
        elapsed = int((datetime.now() - job.start_time).total_seconds())
        mins, secs = divmod(elapsed, 60)
        elapsed_str = f"{mins}m{secs:02d}s" if mins else f"{secs}s"
        panel.set_job_status(rf"[yellow]● {job.title}[/]  [dim]{elapsed_str}  \[b] view output[/]")

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

    # ── Node filter → pod table ───────────────────────────────────────────

    def on_node_table_widget_node_filter_changed(
        self, event: "NodeTableWidget.NodeFilterChanged"
    ) -> None:
        pod_table = self.query_one("#pod-table", PodTableWidget)
        pod_table.node_filter = event.node_name or ""
        self._update_pod_label()

    def on_resource_table_widget_resource_filter_changed(
        self, event: "ResourceTableWidget.ResourceFilterChanged"
    ) -> None:
        pod_table = self.query_one("#pod-table", PodTableWidget)
        pod_table.resource_filter = event.resource_name or ""
        self._update_pod_label()

    def on_data_table_row_selected(self, event: "DataTable.RowSelected") -> None:
        """Enter on pod-datatable opens describe."""
        if event.data_table.id == "pod-datatable":
            pod = self._selected_pod()
            if pod:
                self.app.push_screen(PodDetailScreen(pod))

    def _update_pod_label(self) -> None:
        ns = self._namespaces[self._ns_idx]
        pod_table = self.query_one("#pod-table", PodTableWidget)
        node_f = pod_table.node_filter
        resource_f = pod_table.resource_filter
        node_part = f"node:[bold cyan]{node_f}[/] [dim](n)[/]" if node_f else "[dim](n) node[/]"
        resource_part = (
            f"resource:[bold cyan]{resource_f}[/] [dim](r)[/]"
            if resource_f
            else "[dim](r) resource[/]"
        )
        label = f"[bold]PODS[/]  ns:[cyan]{ns}[/]  {node_part}  {resource_part}  filter:"
        try:
            self.query_one("#pod-filter-label", Label).update(label)
        except Exception:
            pass

    # ── ClusterStateUpdated ────────────────────────────────────────────────

    def on_cluster_state_updated(self, event: ClusterStateUpdated) -> None:
        self._last_cluster_state = event.state
        for widget_id in ["resource-table", "node-table", "pod-table", "status-bar"]:
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

    def action_show_jobs(self) -> None:
        self.app.push_screen(JobsScreen())

    def action_cycle_panel(self) -> None:
        """Tab: cycle focus through resource → node → pod tables."""
        resource_dt = self.query_one("#resource-datatable")
        node_dt = self.query_one("#node-datatable")
        if resource_dt.has_focus:
            node_dt.focus()
        elif node_dt.has_focus:
            self.query_one("#pod-datatable").focus()
        else:
            resource_dt.focus()

    def action_focus_filter(self) -> None:
        inp = self.query_one("#pod-filter-input", Input)
        inp.focus()

    def action_escape_focus(self) -> None:
        """Escape: if filter input is focused, return focus to the pod table."""
        inp = self.query_one("#pod-filter-input", Input)
        if inp.has_focus:
            self.query_one("#pod-datatable").focus()

    def action_toggle_node_filter(self) -> None:
        self.query_one("#node-table", NodeTableWidget).toggle_filter()

    def action_toggle_resource_filter(self) -> None:
        self.query_one("#resource-table", ResourceTableWidget).toggle_filter()

    def action_cycle_namespace(self) -> None:
        # Save current namespace's filter before switching
        old_ns = self._namespaces[self._ns_idx]
        inp = self.query_one("#pod-filter-input", Input)
        self._ns_filters[old_ns] = inp.value
        _save_ns_filters(self._ns_filters)

        self._ns_idx = (self._ns_idx + 1) % len(self._namespaces)
        ns = self._namespaces[self._ns_idx]
        self._collector.namespace = ns

        # Update pod table namespace — triggers immediate client-side re-filter
        pod_table = self.query_one("#pod-table", PodTableWidget)
        pod_table.namespace = ns
        self._update_pod_label()

        # Restore saved filter for the new namespace (setting inp.value triggers on_input_changed)
        inp.value = self._ns_filters.get(ns, "")
        asyncio.ensure_future(self._collector.force_refresh())

    # ── Pod actions ───────────────────────────────────────────────────────

    def _require_pod(self) -> "PodInfo | None":
        return self._selected_pod()

    def action_pod_logs(self) -> None:
        pod = self._require_pod()
        if pod:
            self.app.push_screen(LogsScreen(pod))

    def action_pod_describe(self) -> None:
        pod = self._require_pod()
        if pod:
            self.app.push_screen(PodDetailScreen(pod))

    def action_pod_exec(self) -> None:
        pod = self._require_pod()
        if pod:
            self.app.push_screen(ExecScreen(pod))

    def action_pod_delete(self) -> None:
        pod = self._require_pod()
        if not pod:
            return
        argv = ["kubectl", "delete", "pod", pod.name, "-n", pod.namespace]
        self._require_confirm(
            "X",
            f"delete pod {pod.name}",
            lambda: self.app.push_screen(ActionScreen("delete-pod", argv, auto_close=True)),
        )

    # ── Node actions ──────────────────────────────────────────────────────

    def _require_node(self) -> "NodeInfo | None":
        node = self._selected_node()
        if node is not None and node.is_control_plane:
            return None
        return node

    def action_node_cordon(self) -> None:
        node = self._require_node()
        if not node:
            return
        self._require_confirm(
            "c",
            f"cordon {node.name}",
            lambda: self.app.push_screen(
                ActionScreen("cordon", ["kubectl", "cordon", node.name], auto_close=True)
            ),
        )

    def action_node_uncordon(self) -> None:
        node = self._require_node()
        if not node:
            return
        self._require_confirm(
            "u",
            f"uncordon {node.name}",
            lambda: self.app.push_screen(
                ActionScreen("uncordon", ["kubectl", "uncordon", node.name], auto_close=True)
            ),
        )

    def action_node_drain(self) -> None:
        node = self._require_node()
        if not node:
            return
        argv = ["kubectl", "drain", node.name, "--ignore-daemonsets", "--delete-emptydir-data"]
        self._require_confirm(
            "w",
            f"DRAIN {node.name} — evicts all pods!",
            lambda: self.app.push_screen(ActionScreen("drain", argv, auto_close=True)),
        )

    # ── Tool actions (1–6) ────────────────────────────────────────────────

    def _do_tool(self, key: str) -> None:
        action = ACTIONS_BY_KEY.get(key)
        if not action:
            return

        if self.app.job_manager.is_running:
            job = self.app.job_manager.current_job
            self.notify(
                rf"{job.title} is running — press \[b] to view it.",
                title="Job in progress",
                severity="warning",
                timeout=4.0,
            )
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
        elif action.needs_confirm:
            # No wizard fields, but needs explicit confirmation — show command preview
            argv = action.build_command({})
            self.app.push_screen(
                CommandPreviewScreen(action.name, action.confirm_message, argv),
                callback=lambda confirmed, a=action, v=argv: (
                    self._launch_tool(a, v, a.working_dir) if confirmed else None
                ),
            )
        else:
            self._launch_tool(action, action.build_command({}), action.working_dir)

    def _launch_tool(self, action, argv, cwd) -> None:
        if self.app.job_manager.is_running:
            self.notify(
                "A background job is already running — press [b] to view it.",
                title="Job in progress",
                severity="warning",
                timeout=4.0,
            )
            return
        self.app.job_manager.start(self.app, action.name, argv, cwd)
        self._update_job_indicator()
        self.app.push_screen(JobsScreen())

    def _on_wizard_result(self, result, action) -> None:
        if result is None:
            return
        argv, cwd, dry_run = result
        if not argv:
            return
        self._launch_tool(action, argv, cwd)

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

    # ── Actions panel click passthrough ───────────────────────────────────────

    def on_job_completed(self, event: JobCompleted) -> None:
        job = event.job
        # Clear the running-job indicator and restore normal hints
        try:
            self.query_one("#actions-panel", ActionsPanelWidget).set_job_status(None)
        except Exception:
            pass
        if job.status == "done":
            self.notify(
                rf"{job.title} finished — press \[b] to view output.",
                title="Job completed",
                timeout=6.0,
            )
        else:
            rc = job.returncode if job.returncode is not None else "?"
            self.notify(
                rf"{job.title} failed (exit {rc}) — press \[b] to view output.",
                title="Job failed",
                severity="error",
                timeout=8.0,
            )

    def on_hint_clicked(self, event: HintClicked) -> None:
        dispatch = {
            "1": self.action_tool_1,
            "2": self.action_tool_2,
            "3": self.action_tool_3,
            "4": self.action_tool_4,
            "5": self.action_tool_5,
            "6": self.action_tool_6,
            "`": self.action_show_console,
            "b": self.action_show_jobs,
            "l": self.action_pod_logs,
            "x": self.action_pod_exec,
            "d": self.action_pod_describe,
            "X": self.action_pod_delete,
            "f": self.action_focus_filter,
            "n": self.action_toggle_node_filter,
            "r": self.action_toggle_resource_filter,
            "N": self.action_cycle_namespace,
            "c": self.action_node_cordon,
            "u": self.action_node_uncordon,
            "w": self.action_node_drain,
            "?": self.action_show_help,
            "q": self.action_quit_app,
        }
        fn = dispatch.get(event.key)
        if fn:
            fn()
