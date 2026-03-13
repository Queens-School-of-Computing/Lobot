"""MainScreen: primary btop-style dashboard layout."""

import asyncio
import socket
from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Input, Label, Static

from ..config import CONTROL_PLANE, JUPYTERHUB_NAMESPACE, TOOLS_DIR
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
from .confirm_screen import ConfirmScreen
from .help_screen import HelpScreen
from .logs_screen import LogsScreen
from .pod_detail_screen import PodDetailScreen
from ..actions.definitions import ACTIONS_BY_KEY


_NAMESPACES = [JUPYTERHUB_NAMESPACE, "all"]


class MainScreen(Screen):
    """The primary dashboard screen."""

    BINDINGS = [
        ("q", "quit_app", "Quit"),
        ("r", "force_refresh", "Refresh"),
        ("question_mark", "show_help", "Help"),
        ("1", "tool_1", "image-pull"),
        ("2", "tool_2", "image-cleanup"),
        ("3", "tool_3", "apply-config"),
        ("4", "tool_4", "sync-groups"),
        ("5", "tool_5", "helm upgrade"),
        ("6", "tool_6", "announcement"),
        # Pod actions (handled via key events on the pod table)
        ("l", "pod_logs", "Logs"),
        ("x", "pod_exec", "Exec"),
        ("d", "pod_delete", "Delete pod"),
        ("R", "pod_restart", "Restart pod"),
        ("D", "pod_describe", "Describe pod"),
        ("enter", "pod_describe", "Describe pod"),
        ("slash", "focus_filter", "Filter"),
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

    def compose(self) -> ComposeResult:
        hostname = socket.gethostname()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        yield Label(
            f" [bold cyan]LOBOT[/]  {hostname}  [dim]{now}[/]",
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
                    f"[bold]PODS[/]  ns:[cyan]{_NAMESPACES[self._ns_idx]}[/]  filter:",
                    id="pod-filter-label",
                    markup=True,
                )
                yield Input(placeholder="", id="pod-filter-input")
                yield Static("", id="pod-count-outer")
            yield PodTableWidget(id="pod-table")
        yield ActionsPanelWidget(id="actions-panel")
        yield StatusBarWidget(id="status-bar")

    def on_mount(self) -> None:
        # Update top bar timestamp every second
        self.set_interval(1, self._tick_clock)
        # Focus the pod table by default
        self.query_one("#pod-table").focus()

    def _tick_clock(self) -> None:
        hostname = socket.gethostname()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.query_one("#top-bar", Label).update(
                f" [bold cyan]LOBOT[/]  {hostname}  [dim]{now}[/]"
            )
        except Exception:
            pass

    # ── ClusterStateUpdated: bubble to all child widgets ──────────────────

    def on_cluster_state_updated(self, event: ClusterStateUpdated) -> None:
        # Forward to all widgets that handle it
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
        self.app.exit()

    def action_force_refresh(self) -> None:
        asyncio.ensure_future(self._collector.force_refresh())

    def action_show_help(self) -> None:
        self.app.push_screen(HelpScreen())

    def action_focus_filter(self) -> None:
        self.query_one("#pod-filter-input", Input).focus()

    def action_cycle_namespace(self) -> None:
        self._ns_idx = (self._ns_idx + 1) % len(_NAMESPACES)
        ns = _NAMESPACES[self._ns_idx]
        self._collector.namespace = ns
        try:
            self.query_one("#pod-filter-label", Label).update(
                f"[bold]PODS[/]  ns:[cyan]{ns}[/]  filter:"
            )
        except Exception:
            pass
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
            asyncio.ensure_future(self._do_exec(pod))

    async def _do_exec(self, pod: PodInfo) -> None:
        cmd = ["kubectl", "exec", "-it", pod.name, "-n", pod.namespace, "--", "/bin/bash"]
        async with self.app.suspend():
            proc = await asyncio.create_subprocess_exec(*cmd)
            await proc.wait()

    def action_pod_delete(self) -> None:
        pod = self._selected_pod()
        if pod:
            asyncio.ensure_future(self._do_pod_delete(pod))

    async def _do_pod_delete(self, pod: PodInfo) -> None:
        confirmed = await self.app.push_screen_wait(
            ConfirmScreen(
                f"Delete pod: {pod.name}",
                f"Delete pod [bold]{pod.username}[/] in namespace {pod.namespace}?\n"
                "JupyterHub will NOT automatically respawn it.",
            )
        )
        if confirmed:
            argv = ["kubectl", "delete", "pod", pod.name, "-n", pod.namespace]
            self.app.push_screen(ActionScreen(f"delete-pod", argv))

    def action_pod_restart(self) -> None:
        pod = self._selected_pod()
        if pod:
            asyncio.ensure_future(self._do_pod_restart(pod))

    async def _do_pod_restart(self, pod: PodInfo) -> None:
        confirmed = await self.app.push_screen_wait(
            ConfirmScreen(
                f"Restart pod: {pod.name}",
                f"Delete pod [bold]{pod.username}[/]?\n"
                "JupyterHub will respawn it when the user next accesses their server.",
            )
        )
        if confirmed:
            argv = ["kubectl", "delete", "pod", pod.name, "-n", pod.namespace]
            self.app.push_screen(ActionScreen("restart-pod", argv))

    # ── Node actions ──────────────────────────────────────────────────────

    def action_node_cordon(self) -> None:
        node = self._selected_node()
        if node and not node.is_control_plane:
            asyncio.ensure_future(self._do_node_action("cordon", node))

    def action_node_uncordon(self) -> None:
        node = self._selected_node()
        if node and not node.is_control_plane:
            asyncio.ensure_future(self._do_node_action("uncordon", node))

    async def _do_node_action(self, action: str, node: NodeInfo) -> None:
        confirmed = await self.app.push_screen_wait(
            ConfirmScreen(
                f"{action.capitalize()} node: {node.name}",
                f"Run [bold]kubectl {action} {node.name}[/]?",
            )
        )
        if confirmed:
            argv = ["kubectl", action, node.name]
            self.app.push_screen(ActionScreen(action, argv))

    def action_node_drain(self) -> None:
        node = self._selected_node()
        if node and not node.is_control_plane:
            asyncio.ensure_future(self._do_node_drain(node))

    async def _do_node_drain(self, node: NodeInfo) -> None:
        confirmed = await self.app.push_screen_wait(
            ConfirmScreen(
                f"Drain node: {node.name}",
                f"[bold red]⚠ This will evict all pods from {node.name}![/]\n"
                "Flags: --ignore-daemonsets --delete-emptydir-data",
            )
        )
        if confirmed:
            argv = [
                "kubectl", "drain", node.name,
                "--ignore-daemonsets",
                "--delete-emptydir-data",
            ]
            self.app.push_screen(ActionScreen("drain", argv))

    # ── Tool actions (1–6) ────────────────────────────────────────────────

    async def _run_tool(self, key: str) -> None:
        action = ACTIONS_BY_KEY.get(key)
        if not action:
            return

        # Wizard for parametrised actions, direct confirm for simple ones
        if action.fields or action.has_dry_run:
            result = await self.app.push_screen_wait(ActionWizardScreen(action))
            if result is None:
                return
            argv, cwd, dry_run = result
        else:
            confirmed = await self.app.push_screen_wait(
                ConfirmScreen(action.name, action.confirm_message or f"Run {action.name}?")
            )
            if not confirmed:
                return
            argv = action.build_command({})
            cwd = action.working_dir

        if action.needs_confirm and action.fields and not argv:
            return

        # For non-dry-run destructive actions, re-confirm
        is_dry_run = "--dry-run" in argv
        if action.needs_confirm and not is_dry_run:
            if action.fields:  # wizard already ran, but still confirm the real run
                confirmed = await self.app.push_screen_wait(
                    ConfirmScreen(
                        f"Run {action.name} (LIVE)",
                        action.confirm_message or f"Run {action.name} for real?",
                    )
                )
                if not confirmed:
                    return

        self.app.push_screen(ActionScreen(action.name, argv, cwd=cwd))

    def action_tool_1(self) -> None:
        asyncio.ensure_future(self._run_tool("1"))

    def action_tool_2(self) -> None:
        asyncio.ensure_future(self._run_tool("2"))

    def action_tool_3(self) -> None:
        asyncio.ensure_future(self._run_tool("3"))

    def action_tool_4(self) -> None:
        asyncio.ensure_future(self._run_tool("4"))

    def action_tool_5(self) -> None:
        asyncio.ensure_future(self._run_tool("5"))

    def action_tool_6(self) -> None:
        self.app.push_screen(AnnouncementScreen())
