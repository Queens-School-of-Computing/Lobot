"""Async data collector: polls kubectl and kubectl-view-allocations."""

import asyncio
import json
import math
from datetime import datetime, timezone
from io import StringIO
from typing import Optional

from textual.message import Message
from textual.widget import Widget

from ..config import (
    CONTROL_PLANE, KUBECTL_VIEW_ALLOCATIONS, JUPYTERHUB_NAMESPACE,
    PODS_INTERVAL, NODES_INTERVAL, ALLOC_INTERVAL, DEV_MODE, MAX_TAG_LEN,
)
from .models import ClusterState, LabSummary, NodeInfo, PodInfo


# ---------------------------------------------------------------------------
# Message emitted to the app when new data is ready
# ---------------------------------------------------------------------------

class ClusterStateUpdated(Message):
    def __init__(self, state: ClusterState) -> None:
        super().__init__()
        self.state = state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pod_username(pod_name: str) -> str:
    """Strip jupyter- prefix and unescape -2d→- (mirrors resource_collector.py:116-117)."""
    name = pod_name.removeprefix("jupyter-")
    return name.replace("-2d", "-")


def _parse_image_tag(image: str) -> str:
    """Return the tag portion of an image string, truncated for display."""
    if ":" in image:
        tag = image.split(":")[-1]
    else:
        tag = "latest"
    if len(tag) > MAX_TAG_LEN:
        return tag[:MAX_TAG_LEN] + "…"
    return tag


def _age_string(start_time_str: Optional[str]) -> str:
    """Convert ISO8601 start time to human-readable age."""
    if not start_time_str:
        return "?"
    try:
        start = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - start
        total_seconds = int(delta.total_seconds())
        if total_seconds < 60:
            return f"{total_seconds}s"
        elif total_seconds < 3600:
            return f"{total_seconds // 60}m"
        elif total_seconds < 86400:
            return f"{total_seconds // 3600}h{(total_seconds % 3600) // 60}m"
        else:
            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            return f"{days}d{hours}h"
    except Exception:
        return "?"


def _cpu_to_cores(value) -> int:
    """Convert CPU value from allocations CSV (may be float millicore string) to int cores."""
    try:
        return math.floor(float(value))
    except (TypeError, ValueError):
        return 0


def _bytes_to_gb(value) -> int:
    """Convert bytes (float) to GB integer."""
    try:
        return math.floor(float(value) / 1_073_741_824)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# Async kubectl helpers
# ---------------------------------------------------------------------------

async def _run_kubectl(*args) -> tuple[str, str, int]:
    """Run kubectl with given args, return (stdout, stderr, returncode)."""
    proc = await asyncio.create_subprocess_exec(
        "kubectl", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return stdout.decode(errors="replace"), stderr.decode(errors="replace"), proc.returncode


async def _run_allocations() -> tuple[str, str, int]:
    """Run kubectl-view-allocations, return (stdout, stderr, returncode)."""
    proc = await asyncio.create_subprocess_exec(
        KUBECTL_VIEW_ALLOCATIONS, "-o", "csv",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return stdout.decode(errors="replace"), stderr.decode(errors="replace"), proc.returncode


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_pods(json_str: str, namespace: str, node_lab_map: dict) -> list:
    """Parse kubectl get pods -o json output into PodInfo list."""
    pods = []
    try:
        data = json.loads(json_str)
        items = data.get("items", [])
    except json.JSONDecodeError:
        return pods

    for item in items:
        try:
            meta = item.get("metadata", {})
            spec = item.get("spec", {})
            status = item.get("status", {})

            name = meta.get("name", "")
            ns = meta.get("namespace", namespace)
            node = spec.get("nodeName", "")
            phase = status.get("phase", "Unknown")
            start_time = status.get("startTime")

            # Image from first container
            containers = spec.get("containers", [{}])
            image = containers[0].get("image", "") if containers else ""
            image_tag = _parse_image_tag(image)

            # Resources from first container requests
            resources = containers[0].get("resources", {}) if containers else {}
            requests = resources.get("requests", {})
            cpu_raw = requests.get("cpu", "0")
            mem_raw = requests.get("memory", "0")
            gpu_raw = requests.get("nvidia.com/gpu", "0")

            cpu = _parse_cpu_request(cpu_raw)
            ram_gb = _parse_memory_request_gb(mem_raw)
            gpu = _parse_gpu_request(gpu_raw)

            username = _pod_username(name)
            lab = node_lab_map.get(node, "")
            age = _age_string(start_time)

            pods.append(PodInfo(
                name=name,
                username=username,
                namespace=ns,
                node=node,
                lab=lab,
                image=image,
                image_tag=image_tag,
                cpu_requested=cpu,
                ram_requested_gb=ram_gb,
                gpu_requested=gpu,
                age=age,
                phase=phase,
                start_time=start_time,
            ))
        except Exception:
            continue

    return sorted(pods, key=lambda p: p.username.lower())


def _parse_cpu_request(raw: str) -> int:
    """Parse k8s CPU request string (e.g. '4', '500m') to integer cores."""
    try:
        if raw.endswith("m"):
            return math.floor(int(raw[:-1]) / 1000)
        return math.floor(float(raw))
    except (ValueError, AttributeError):
        return 0


def _parse_memory_request_gb(raw: str) -> int:
    """Parse k8s memory request string (e.g. '128Gi', '512Mi') to GB."""
    try:
        if raw.endswith("Ki"):
            return math.floor(int(raw[:-2]) / 1_048_576)
        elif raw.endswith("Mi"):
            return math.floor(int(raw[:-2]) / 1024)
        elif raw.endswith("Gi"):
            return int(raw[:-2])
        elif raw.endswith("Ti"):
            return int(raw[:-2]) * 1024
        elif raw.endswith("G"):
            return int(raw[:-1])
        elif raw.endswith("M"):
            return math.floor(int(raw[:-1]) / 1024)
        else:
            return _bytes_to_gb(raw)
    except (ValueError, AttributeError):
        return 0


def _parse_gpu_request(raw: str) -> int:
    try:
        return int(raw)
    except (ValueError, TypeError):
        return 0


def _parse_nodes(json_str: str) -> tuple[dict, list]:
    """
    Parse kubectl get nodes --show-labels -o json.
    Returns (node_lab_map: {node_name: lab}, partial_nodes: [NodeInfo with alloc fields=0]).
    """
    node_lab_map = {}
    partial_nodes = []
    try:
        data = json.loads(json_str)
        items = data.get("items", [])
    except json.JSONDecodeError:
        return node_lab_map, partial_nodes

    for item in items:
        try:
            meta = item.get("metadata", {})
            spec = item.get("spec", {})
            status_obj = item.get("status", {})

            name = meta.get("name", "")
            labels = meta.get("labels", {})
            lab = labels.get("lab", "")

            # Determine if control plane
            is_ctrl = (
                name == CONTROL_PLANE
                or "node-role.kubernetes.io/control-plane" in labels
                or "node-role.kubernetes.io/master" in labels
            )

            # Node ready status
            conditions = status_obj.get("conditions", [])
            ready_status = "Unknown"
            for cond in conditions:
                if cond.get("type") == "Ready":
                    ready_status = "Ready" if cond.get("status") == "True" else "NotReady"
                    break

            schedulable = not spec.get("unschedulable", False)

            node_lab_map[name] = lab
            partial_nodes.append(NodeInfo(
                name=name,
                lab=lab,
                status=ready_status,
                schedulable=schedulable,
                cpu_allocatable=0,
                cpu_requested=0,
                ram_allocatable_gb=0,
                ram_requested_gb=0,
                gpu_allocatable=0,
                gpu_requested=0,
                is_control_plane=is_ctrl,
            ))
        except Exception:
            continue

    return node_lab_map, partial_nodes


def _parse_allocations(csv_str: str, node_lab_map: dict, partial_nodes: list) -> tuple[list, dict]:
    """
    Parse kubectl-view-allocations CSV output.
    Returns (nodes: [NodeInfo], labs: {lab: LabSummary}).
    """
    # Build a lookup of partial node info
    node_lookup = {n.name: n for n in partial_nodes}

    # Parse CSV manually (avoid pandas dependency in TUI)
    lines = csv_str.strip().splitlines()
    if len(lines) < 2:
        return list(node_lookup.values()), {}

    # CSV columns: node,resource,Kind,Requested,%Requested,Limit,%Limit,Allocatable,Free
    # (actual columns from kubectl-view-allocations may vary — use header to find indices)
    header = [h.strip() for h in lines[0].split(",")]
    try:
        idx_node = header.index("node")
        idx_resource = header.index("resource")
        idx_kind = header.index("Kind")
        idx_requested = header.index("Requested")
        idx_allocatable = header.index("Allocatable")
    except ValueError:
        return list(node_lookup.values()), {}

    # Aggregate per-node
    node_cpu_alloc: dict = {}
    node_cpu_req: dict = {}
    node_mem_alloc: dict = {}
    node_mem_req: dict = {}
    node_gpu_alloc: dict = {}
    node_gpu_req: dict = {}

    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) <= max(idx_node, idx_resource, idx_kind, idx_requested, idx_allocatable):
            continue
        try:
            node = parts[idx_node].strip()
            resource = parts[idx_resource].strip()
            kind = parts[idx_kind].strip()
            requested_raw = parts[idx_requested].strip()
            allocatable_raw = parts[idx_allocatable].strip()

            if kind != "node":
                continue

            if resource == "cpu":
                node_cpu_alloc[node] = node_cpu_alloc.get(node, 0) + _cpu_to_cores(allocatable_raw)
                node_cpu_req[node] = node_cpu_req.get(node, 0) + _cpu_to_cores(requested_raw)
            elif resource == "memory":
                node_mem_alloc[node] = node_mem_alloc.get(node, 0) + _bytes_to_gb(allocatable_raw)
                node_mem_req[node] = node_mem_req.get(node, 0) + _bytes_to_gb(requested_raw)
            elif resource == "nvidia.com/gpu":
                node_gpu_alloc[node] = node_gpu_alloc.get(node, 0) + _cpu_to_cores(allocatable_raw)
                node_gpu_req[node] = node_gpu_req.get(node, 0) + _cpu_to_cores(requested_raw)
        except Exception:
            continue

    # Build final NodeInfo list with allocation data
    all_node_names = set(node_lookup.keys()) | set(node_cpu_alloc.keys())
    nodes = []
    for name in all_node_names:
        partial = node_lookup.get(name)
        if partial is None:
            lab = node_lab_map.get(name, "")
            partial = NodeInfo(
                name=name, lab=lab, status="Unknown", schedulable=True,
                cpu_allocatable=0, cpu_requested=0,
                ram_allocatable_gb=0, ram_requested_gb=0,
                gpu_allocatable=0, gpu_requested=0,
                is_control_plane=(name == CONTROL_PLANE),
            )
        nodes.append(NodeInfo(
            name=partial.name,
            lab=partial.lab,
            status=partial.status,
            schedulable=partial.schedulable,
            cpu_allocatable=node_cpu_alloc.get(name, partial.cpu_allocatable),
            cpu_requested=node_cpu_req.get(name, partial.cpu_requested),
            ram_allocatable_gb=node_mem_alloc.get(name, partial.ram_allocatable_gb),
            ram_requested_gb=node_mem_req.get(name, partial.ram_requested_gb),
            gpu_allocatable=node_gpu_alloc.get(name, partial.gpu_allocatable),
            gpu_requested=node_gpu_req.get(name, partial.gpu_requested),
            is_control_plane=partial.is_control_plane,
        ))

    # Build LabSummary from node aggregates
    labs: dict = {}
    for node in nodes:
        if not node.lab or node.is_control_plane:
            continue
        lab_name = node.lab
        if lab_name not in labs:
            labs[lab_name] = LabSummary(
                name=lab_name,
                cpu_free=0, cpu_total=0,
                ram_free_gb=0, ram_total_gb=0,
                gpu_free=0, gpu_total=0,
            )
        s = labs[lab_name]
        s.cpu_total += node.cpu_allocatable
        s.cpu_free += node.cpu_free
        s.ram_total_gb += node.ram_allocatable_gb
        s.ram_free_gb += node.ram_free_gb
        s.gpu_total += node.gpu_allocatable
        s.gpu_free += node.gpu_free

    return nodes, labs


# ---------------------------------------------------------------------------
# Mock data for local dev/testing (LOBOT_TUI_DEV=1)
# ---------------------------------------------------------------------------

def _mock_state() -> ClusterState:
    from .models import LabSummary, PodInfo, NodeInfo, ClusterState
    now = datetime.now()
    labs = {
        "lobot_a40": LabSummary("lobot_a40", 191, 256, 1694, 2014, 5, 8, pod_count=3),
        "lobot_a5000": LabSummary("lobot_a5000", 153, 256, 368, 1008, 4, 8, pod_count=3),
        "miblab": LabSummary("miblab", 104, 192, 495, 1007, 2, 6, pod_count=1),
        "gandslab": LabSummary("gandslab", 68, 128, 27, 251, 2, 2, pod_count=3),
        "riselab": LabSummary("riselab", 183, 256, 688, 1008, 5, 7, pod_count=5),
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
        labs=labs, pods=pods, nodes=nodes,
        last_pods_update=now, last_nodes_update=now, last_alloc_update=now,
    )


# ---------------------------------------------------------------------------
# DataCollector
# ---------------------------------------------------------------------------

class DataCollector:
    """
    Async background collector. Call start() once to launch polling tasks.
    Emits ClusterStateUpdated messages on the provided poster widget.
    """

    def __init__(self, poster: Widget) -> None:
        self._poster = poster
        self._state = ClusterState()
        self._node_lab_map: dict = {}
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
        asyncio.ensure_future(self._poll_allocations())

    async def _poll_pods(self) -> None:
        while True:
            await self._fetch_pods()
            await asyncio.sleep(PODS_INTERVAL)

    async def _poll_nodes(self) -> None:
        while True:
            await self._fetch_nodes()
            await asyncio.sleep(NODES_INTERVAL)

    async def _poll_allocations(self) -> None:
        while True:
            await self._fetch_allocations()
            await asyncio.sleep(ALLOC_INTERVAL)

    async def _fetch_pods(self) -> None:
        ns_args = ["get", "pods", "-o", "json"]
        if self._namespace == "all":
            ns_args = ["get", "pods", "--all-namespaces", "-o", "json"]
        else:
            ns_args = ["get", "pods", "-n", self._namespace, "-o", "json"]

        stdout, stderr, rc = await _run_kubectl(*ns_args)
        async with self._lock:
            if rc == 0:
                self._state.pods = _parse_pods(stdout, self._namespace, self._node_lab_map)
                self._state.last_pods_update = datetime.now()
                self._state.pods_error = None
                # Update pod_count on labs
                pod_lab_counts: dict = {}
                for pod in self._state.pods:
                    pod_lab_counts[pod.lab] = pod_lab_counts.get(pod.lab, 0) + 1
                for lab_name, lab in self._state.labs.items():
                    lab.pod_count = pod_lab_counts.get(lab_name, 0)
            else:
                self._state.pods_error = stderr.strip() or "kubectl error"
            self._poster.post_message(ClusterStateUpdated(self._state))

    async def _fetch_nodes(self) -> None:
        stdout, stderr, rc = await _run_kubectl(
            "get", "nodes", "--show-labels", "-o", "json"
        )
        async with self._lock:
            if rc == 0:
                node_lab_map, partial_nodes = _parse_nodes(stdout)
                self._node_lab_map = node_lab_map
                self._partial_nodes = partial_nodes
                self._state.last_nodes_update = datetime.now()
                self._state.nodes_error = None
            else:
                self._state.nodes_error = stderr.strip() or "kubectl error"
            self._poster.post_message(ClusterStateUpdated(self._state))

    async def _fetch_allocations(self) -> None:
        stdout, stderr, rc = await _run_allocations()
        async with self._lock:
            if rc == 0:
                nodes, labs = _parse_allocations(stdout, self._node_lab_map, self._partial_nodes)
                self._state.nodes = nodes
                self._state.labs = labs
                self._state.last_alloc_update = datetime.now()
                self._state.alloc_error = None
                # Re-count pods per lab after lab refresh
                pod_lab_counts: dict = {}
                for pod in self._state.pods:
                    pod_lab_counts[pod.lab] = pod_lab_counts.get(pod.lab, 0) + 1
                for lab_name, lab in labs.items():
                    lab.pod_count = pod_lab_counts.get(lab_name, 0)
            else:
                self._state.alloc_error = stderr.strip() or "kubectl-view-allocations error"
            self._poster.post_message(ClusterStateUpdated(self._state))

    async def force_refresh(self) -> None:
        """Trigger an immediate refresh of all data sources."""
        await asyncio.gather(
            self._fetch_pods(),
            self._fetch_nodes(),
            self._fetch_allocations(),
        )
