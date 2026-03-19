"""Async kubectl polling loop for lobot-collector service."""

import asyncio
import logging
from datetime import datetime

from lobot_tui.data.models import ClusterState
from lobot_tui.data.parsers import (
    _merge_nodes_and_pods,
    _parse_longhorn_nodes,
    _parse_nodes,
    _parse_pods,
    _run_kubectl,
)

from .config import (
    JUPYTERHUB_NAMESPACE,
    LONGHORN_INTERVAL,
    LONGHORN_NAMESPACE,
    NODES_INTERVAL,
    PODS_INTERVAL,
)

logger = logging.getLogger(__name__)


class ClusterCollector:
    """
    Polls kubectl every PODS_INTERVAL / NODES_INTERVAL seconds.
    Maintains a ClusterState in memory and notifies all SSE subscribers on
    every update via per-client asyncio.Queue objects.
    """

    def __init__(self) -> None:
        self._state = ClusterState()
        self._node_resource_map: dict = {}
        self._partial_nodes: list = []
        self._lock = asyncio.Lock()
        self._subscribers: set[asyncio.Queue] = set()
        self._namespace = JUPYTERHUB_NAMESPACE

    # ── Subscriber management (one Queue per SSE client) ──────────────────────

    def subscribe(self) -> asyncio.Queue:
        """Register a new SSE subscriber; returns its event queue."""
        q: asyncio.Queue = asyncio.Queue(maxsize=1)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    @property
    def state(self) -> ClusterState:
        return self._state

    # ── Startup ───────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Launch background polling tasks."""
        asyncio.ensure_future(self._poll_pods())
        asyncio.ensure_future(self._poll_nodes())
        asyncio.ensure_future(self._poll_longhorn())

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _notify(self) -> None:
        """Push current state to all waiting SSE clients."""
        for q in list(self._subscribers):
            if q.full():
                # Drop the stale item so the client always gets the latest state
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(self._state)
            except asyncio.QueueFull:
                pass

    async def _poll_pods(self) -> None:
        while True:
            await self._fetch_pods()
            await asyncio.sleep(PODS_INTERVAL)

    async def _poll_nodes(self) -> None:
        while True:
            await self._fetch_nodes()
            await asyncio.sleep(NODES_INTERVAL)

    async def _poll_longhorn(self) -> None:
        while True:
            await self._fetch_longhorn()
            await asyncio.sleep(LONGHORN_INTERVAL)

    async def _fetch_pods(self) -> None:
        stdout, stderr, rc = await _run_kubectl("get", "pods", "--all-namespaces", "-o", "json")
        async with self._lock:
            if rc == 0:
                self._state.pods = _parse_pods(stdout, "all", self._node_resource_map)
                self._state.last_pods_update = datetime.now()
                self._state.pods_error = None
                nodes, resources = _merge_nodes_and_pods(self._partial_nodes, self._state.pods)
                self._state.nodes = nodes
                self._state.resources = resources
                pod_resource_counts: dict = {}
                for pod in self._state.pods:
                    if pod.name.startswith("jupyter-"):
                        pod_resource_counts[pod.resource] = (
                            pod_resource_counts.get(pod.resource, 0) + 1
                        )
                for resource_name, resource in self._state.resources.items():
                    resource.pod_count = pod_resource_counts.get(resource_name, 0)
            else:
                self._state.pods_error = stderr.strip() or "kubectl error"
                logger.error("kubectl get pods failed: %s", stderr.strip())
            await self._notify()

    async def _fetch_nodes(self) -> None:
        stdout, stderr, rc = await _run_kubectl("get", "nodes", "-o", "json")
        async with self._lock:
            if rc == 0:
                node_resource_map, partial_nodes = _parse_nodes(stdout)
                self._node_resource_map = node_resource_map
                self._partial_nodes = partial_nodes
                self._state.last_nodes_update = datetime.now()
                self._state.nodes_error = None
                nodes, resources = _merge_nodes_and_pods(self._partial_nodes, self._state.pods)
                self._state.nodes = nodes
                self._state.resources = resources
                pod_resource_counts: dict = {}
                for pod in self._state.pods:
                    if pod.name.startswith("jupyter-"):
                        pod_resource_counts[pod.resource] = (
                            pod_resource_counts.get(pod.resource, 0) + 1
                        )
                for resource_name, resource in self._state.resources.items():
                    resource.pod_count = pod_resource_counts.get(resource_name, 0)
            else:
                self._state.nodes_error = stderr.strip() or "kubectl error"
                logger.error("kubectl get nodes failed: %s", stderr.strip())
            await self._notify()

    async def _fetch_longhorn(self) -> None:
        stdout, stderr, rc = await _run_kubectl(
            "get", "nodes.longhorn.io", "-n", LONGHORN_NAMESPACE, "-o", "json"
        )
        async with self._lock:
            if rc == 0:
                self._state.longhorn_disks = _parse_longhorn_nodes(stdout)
                self._state.last_longhorn_update = datetime.now()
            else:
                logger.warning("kubectl get nodes.longhorn.io failed: %s", stderr.strip())
            await self._notify()
