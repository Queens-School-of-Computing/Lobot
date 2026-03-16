"""Async data collector: polls kubectl for pod and node data."""

import asyncio
import json
from datetime import datetime

from textual.message import Message
from textual.widget import Widget

from ..config import (
    CONTROL_PLANE, JUPYTERHUB_NAMESPACE,
    PODS_INTERVAL, NODES_INTERVAL, DEV_MODE,
    SERVICE_HOST, SERVICE_PORT,
)
from .models import ClusterState, ResourceSummary, NodeInfo, PodInfo
from .parsers import (
    _run_kubectl,
    _parse_pods, _parse_nodes, _merge_nodes_and_pods,
)


# ---------------------------------------------------------------------------
# Message emitted to the app when new data is ready
# ---------------------------------------------------------------------------

class ClusterStateUpdated(Message):
    def __init__(self, state: ClusterState, source: str = "kubectl") -> None:
        super().__init__()
        self.state = state
        self.source = source  # "service" or "kubectl"


# ---------------------------------------------------------------------------
# Mock data for local dev/testing (LOBOT_TUI_DEV=1)
# ---------------------------------------------------------------------------

def _mock_state() -> ClusterState:
    now = datetime.now()
    resources = {
        "lobot_a40": ResourceSummary("lobot_a40", 191, 256, 1694, 2014, 5, 8, pod_count=3),
        "lobot_a5000": ResourceSummary("lobot_a5000", 153, 256, 368, 1008, 4, 8, pod_count=3),
        "miblab": ResourceSummary("miblab", 104, 192, 495, 1007, 2, 6, pod_count=1),
        "gandslab": ResourceSummary("gandslab", 68, 128, 27, 251, 2, 2, pod_count=3),
        "riselab": ResourceSummary("riselab", 183, 256, 688, 1008, 5, 7, pod_count=5),
    }
    pods = [
        PodInfo("jupyter-ruslanamruddin", "ruslanamruddin", "jhub", "newcluster-gpu1", "lobot_a40",
                "queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn", "13.0.2cudnn…", 10, 128, 1, "2d3h", "Running"),
        PodInfo("jupyter-busvp52", "busvp52", "jhub", "newcluster-gpu1", "lobot_a40",
                "queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn", "13.0.2cudnn…", 16, 128, 1, "1d1h", "Running"),
        PodInfo("jupyter-qscautodrivegroup2", "qscautodrivegroup2", "jhub", "newcluster-gpu2", "lobot_a40",
                "queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn", "13.0.2cudnn…", 8, 64, 1, "5h12m", "Running"),
        PodInfo("jupyter-ryanz8", "ryanz8", "jhub", "newcluster-gpu3", "miblab",
                "queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn", "13.0.2cudnn…", 64, 512, 4, "3d", "Running"),
        PodInfo("jupyter-maxhao56", "maxhao56", "jhub", "newcluster-gpu4", "riselab",
                "queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn", "13.0.2cudnn…", 10, 64, 2, "4h", "Running"),
        PodInfo("jupyter-pending-2duser", "pending-user", "jhub", "", "lobot_a5000",
                "queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn", "13.0.2cudnn…", 8, 64, 1, "2m", "Pending"),
    ]
    nodes = [
        NodeInfo("newcluster-gpu1", "lobot_a40", "Ready", True, 64, 26, 503, 256, 2, 2),
        NodeInfo("newcluster-gpu2", "lobot_a40", "Ready", True, 64, 8, 503, 64, 2, 1),
        NodeInfo("newcluster-gpu3", "miblab", "Ready", True, 64, 64, 503, 512, 4, 4),
        NodeInfo("newcluster-gpu4", "riselab", "Ready", False, 64, 10, 503, 64, 2, 2),
        NodeInfo(CONTROL_PLANE, "", "Ready", True, 16, 2, 32, 4, 0, 0, is_control_plane=True),
    ]
    return ClusterState(
        resources=resources, pods=pods, nodes=nodes,
        last_pods_update=now, last_nodes_update=now,
    )


# ---------------------------------------------------------------------------
# DataCollector — direct kubectl polling (used when service is unavailable)
# ---------------------------------------------------------------------------

class DataCollector:
    """
    Async background collector. Call start() once to launch polling tasks.
    Emits ClusterStateUpdated messages on the provided poster widget.
    """

    def __init__(self, poster: Widget) -> None:
        self._poster = poster
        self._state = ClusterState()
        self._node_resource_map: dict = {}
        self._partial_nodes: list = []
        self._namespace = JUPYTERHUB_NAMESPACE
        self._lock = asyncio.Lock()

    @property
    def namespace(self) -> str:
        return self._namespace

    @namespace.setter
    def namespace(self, value: str) -> None:
        self._namespace = value

    def start(self) -> None:
        """Launch background polling tasks."""
        if DEV_MODE:
            self._state = _mock_state()
            self._poster.post_message(ClusterStateUpdated(self._state))
            return
        asyncio.ensure_future(self._poll_pods())
        asyncio.ensure_future(self._poll_nodes())

    async def _poll_pods(self) -> None:
        while True:
            await self._fetch_pods()
            await asyncio.sleep(PODS_INTERVAL)

    async def _poll_nodes(self) -> None:
        while True:
            await self._fetch_nodes()
            await asyncio.sleep(NODES_INTERVAL)

    async def _fetch_pods(self) -> None:
        if self._namespace == "all":
            ns_args = ["get", "pods", "--all-namespaces", "-o", "json"]
        else:
            ns_args = ["get", "pods", "-n", self._namespace, "-o", "json"]

        stdout, stderr, rc = await _run_kubectl(*ns_args)
        async with self._lock:
            if rc == 0:
                self._state.pods = _parse_pods(stdout, self._namespace, self._node_resource_map)
                self._state.last_pods_update = datetime.now()
                self._state.pods_error = None
                nodes, resources = _merge_nodes_and_pods(self._partial_nodes, self._state.pods)
                self._state.nodes = nodes
                self._state.resources = resources
                pod_resource_counts: dict = {}
                for pod in self._state.pods:
                    if pod.name.startswith("jupyter-"):
                        pod_resource_counts[pod.resource] = pod_resource_counts.get(pod.resource, 0) + 1
                for resource_name, resource in self._state.resources.items():
                    resource.pod_count = pod_resource_counts.get(resource_name, 0)
            else:
                self._state.pods_error = stderr.strip() or "kubectl error"
            self._poster.post_message(ClusterStateUpdated(self._state))

    async def _fetch_nodes(self) -> None:
        stdout, stderr, rc = await _run_kubectl(
            "get", "nodes", "-o", "json"
        )
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
                        pod_resource_counts[pod.resource] = pod_resource_counts.get(pod.resource, 0) + 1
                for resource_name, resource in self._state.resources.items():
                    resource.pod_count = pod_resource_counts.get(resource_name, 0)
            else:
                self._state.nodes_error = stderr.strip() or "kubectl error"
            self._poster.post_message(ClusterStateUpdated(self._state))

    async def force_refresh(self) -> None:
        """Trigger an immediate refresh of all data sources."""
        await asyncio.gather(
            self._fetch_pods(),
            self._fetch_nodes(),
        )


# ---------------------------------------------------------------------------
# ServiceCollector — polls lobot-collector /api/state on the same interval
# ---------------------------------------------------------------------------

class ServiceCollector:
    """
    Polls the lobot-collector HTTP service for ClusterState every PODS_INTERVAL
    seconds.  Drop-in replacement for DataCollector — same start() interface.
    Using periodic HTTP polling (rather than SSE) avoids chunked-encoding
    complexity and is equally reliable for a 5-second update cycle.

    The service always returns all-namespace pod data; namespace filtering is
    done client-side in PodTableWidget, not here.
    """

    def __init__(self, poster: Widget) -> None:
        self._poster = poster
        self._namespace = JUPYTERHUB_NAMESPACE

    @property
    def namespace(self) -> str:
        return self._namespace

    @namespace.setter
    def namespace(self, value: str) -> None:
        self._namespace = value

    def start(self) -> None:
        asyncio.ensure_future(self._poll())

    async def _poll(self) -> None:
        while True:
            await self._fetch()
            await asyncio.sleep(PODS_INTERVAL)

    async def _fetch(self) -> None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(SERVICE_HOST, SERVICE_PORT), timeout=2.0
            )
            try:
                # Connection: close tells HTTP/1.1 server to close after response,
                # so read(-1) sees EOF instead of blocking on keep-alive.
                writer.write(
                    b"GET /api/state HTTP/1.1\r\n"
                    b"Host: localhost\r\n"
                    b"Connection: close\r\n"
                    b"\r\n"
                )
                await writer.drain()
                # Skip HTTP response headers, capture Content-Length if present
                content_length = None
                while True:
                    line = await asyncio.wait_for(reader.readline(), timeout=5.0)
                    if not line or line in (b"\r\n", b"\n"):
                        break
                    if line.lower().startswith(b"content-length:"):
                        content_length = int(line.split(b":", 1)[1].strip())
                if content_length is not None:
                    body = await asyncio.wait_for(
                        reader.readexactly(content_length), timeout=10.0
                    )
                else:
                    body = await asyncio.wait_for(reader.read(-1), timeout=10.0)
                state = ClusterState.from_dict(json.loads(body))
                self._poster.post_message(ClusterStateUpdated(state, source="service"))
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
        except Exception:
            pass

    async def force_refresh(self) -> None:
        await self._fetch()
