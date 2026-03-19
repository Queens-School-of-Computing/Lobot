"""Pure kubectl parsing functions — no Textual dependency.

These functions are shared between lobot-tui and the lobot-collector service.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

from ..config import CONTROL_PLANE, MAX_TAG_LEN
from .models import DiskInfo, NodeInfo, PodInfo, ResourceSummary

# ---------------------------------------------------------------------------
# String helpers
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
        return "…" + tag[-(MAX_TAG_LEN - 1) :]
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


# ---------------------------------------------------------------------------
# Resource unit parsers
# ---------------------------------------------------------------------------


def _parse_cpu_request(raw: str) -> float:
    """Parse k8s CPU request string (e.g. '4', '500m') to fractional cores."""
    try:
        if raw.endswith("m"):
            return round(int(raw[:-1]) / 1000, 3)
        return float(raw)
    except (ValueError, AttributeError):  # fmt: skip
        return 0.0


def _parse_memory_request_gb(raw: str) -> float:
    """Parse k8s memory request string (e.g. '128Gi', '512Mi') to fractional GB."""
    try:
        if raw.endswith("Ki"):
            return int(raw[:-2]) / 1_048_576
        elif raw.endswith("Mi"):
            return int(raw[:-2]) / 1024
        elif raw.endswith("Gi"):
            return float(raw[:-2])
        elif raw.endswith("Ti"):
            return float(raw[:-2]) * 1024
        elif raw.endswith("G"):
            return float(raw[:-1])
        elif raw.endswith("M"):
            return int(raw[:-1]) / 1024
        else:
            return float(raw) / 1_073_741_824
    except (ValueError, AttributeError):  # fmt: skip
        return 0.0


def _parse_gpu_request(raw: str) -> int:
    try:
        return int(raw)
    except (ValueError, TypeError):  # fmt: skip
        return 0


# ---------------------------------------------------------------------------
# Async kubectl runner
# ---------------------------------------------------------------------------


async def _run_kubectl(*args) -> tuple[str, str, int]:
    """Run kubectl with given args, return (stdout, stderr, returncode)."""
    proc = await asyncio.create_subprocess_exec(
        "kubectl",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return stdout.decode(errors="replace"), stderr.decode(errors="replace"), proc.returncode


# ---------------------------------------------------------------------------
# kubectl output parsers
# ---------------------------------------------------------------------------


def _parse_pods(json_str: str, namespace: str, node_resource_map: dict) -> list:
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
            resource = node_resource_map.get(node, "")
            age = _age_string(start_time)

            pods.append(
                PodInfo(
                    name=name,
                    username=username,
                    namespace=ns,
                    node=node,
                    resource=resource,
                    image=image,
                    image_tag=image_tag,
                    cpu_requested=cpu,
                    ram_requested_gb=ram_gb,
                    gpu_requested=gpu,
                    age=age,
                    phase=phase,
                    start_time=start_time,
                )
            )
        except Exception:
            continue

    return sorted(pods, key=lambda p: p.username.lower())


def _parse_nodes(json_str: str) -> tuple[dict, list]:
    """
    Parse kubectl get nodes -o json.
    Returns (node_resource_map: {node_name: resource}, partial_nodes: [NodeInfo with alloc fields=0]).
    Note: reads the Kubernetes node label key 'lab' which maps to the resource group name.
    """
    node_resource_map = {}
    partial_nodes = []
    try:
        data = json.loads(json_str)
        items = data.get("items", [])
    except json.JSONDecodeError:
        return node_resource_map, partial_nodes

    for item in items:
        try:
            meta = item.get("metadata", {})
            spec = item.get("spec", {})
            status_obj = item.get("status", {})

            name = meta.get("name", "")
            labels = meta.get("labels", {})
            resource = labels.get("lab", "")  # K8s node label key is 'lab'

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

            # Parse allocatable resources directly from node status.
            # CPU is always whole cores; RAM rounded to 1 decimal GB.
            alloc = status_obj.get("allocatable", {})
            cpu_allocatable = int(round(_parse_cpu_request(alloc.get("cpu", "0"))))
            ram_allocatable_gb = round(_parse_memory_request_gb(alloc.get("memory", "0")), 1)
            gpu_allocatable = _parse_gpu_request(alloc.get("nvidia.com/gpu", "0"))

            node_resource_map[name] = resource
            partial_nodes.append(
                NodeInfo(
                    name=name,
                    resource=resource,
                    status=ready_status,
                    schedulable=schedulable,
                    cpu_allocatable=cpu_allocatable,
                    cpu_requested=0,  # filled by _merge_nodes_and_pods
                    ram_allocatable_gb=ram_allocatable_gb,
                    ram_requested_gb=0,
                    gpu_allocatable=gpu_allocatable,
                    gpu_requested=0,
                    is_control_plane=is_ctrl,
                )
            )
        except Exception:
            continue

    return node_resource_map, partial_nodes


def _merge_nodes_and_pods(partial_nodes: list, pods: list) -> tuple[list, dict]:
    """
    Compute final NodeInfo (with requested resources) and ResourceSummary by
    aggregating pod resource requests per node.

    partial_nodes must already carry allocatable values (populated by _parse_nodes).
    pods is the current pod list from _parse_pods.
    """
    # Sum ALL pod requests by node (used for NodeInfo — node panel shows everything)
    node_cpu_req: dict = {}
    node_ram_req: dict = {}
    node_gpu_req: dict = {}
    # Sum only jupyter-* pod requests by node (used for ResourceSummary — user workloads only)
    node_cpu_jupyter: dict = {}
    node_ram_jupyter: dict = {}
    node_gpu_jupyter: dict = {}
    for pod in pods:
        n = pod.node
        if not n:
            continue
        node_cpu_req[n] = node_cpu_req.get(n, 0) + pod.cpu_requested
        node_ram_req[n] = node_ram_req.get(n, 0) + pod.ram_requested_gb
        node_gpu_req[n] = node_gpu_req.get(n, 0) + pod.gpu_requested
        if pod.name.startswith("jupyter-"):
            node_cpu_jupyter[n] = node_cpu_jupyter.get(n, 0) + pod.cpu_requested
            node_ram_jupyter[n] = node_ram_jupyter.get(n, 0) + pod.ram_requested_gb
            node_gpu_jupyter[n] = node_gpu_jupyter.get(n, 0) + pod.gpu_requested

    # Merge with allocatable to produce final NodeInfo list.
    # Pod requests are float; round to int for node-level display (allocatable is always whole).
    nodes = [
        NodeInfo(
            name=pn.name,
            resource=pn.resource,
            status=pn.status,
            schedulable=pn.schedulable,
            cpu_allocatable=pn.cpu_allocatable,
            cpu_requested=round(node_cpu_req.get(pn.name, 0)),
            ram_allocatable_gb=pn.ram_allocatable_gb,
            ram_requested_gb=round(node_ram_req.get(pn.name, 0), 1),
            gpu_allocatable=pn.gpu_allocatable,
            gpu_requested=node_gpu_req.get(pn.name, 0),
            is_control_plane=pn.is_control_plane,
        )
        for pn in partial_nodes
    ]

    # Aggregate by resource group — jupyter-* requests only so the resource panel
    # reflects user workload pressure, not system pod overhead.
    resources: dict = {}
    for node in nodes:
        if not node.resource or node.is_control_plane:
            continue
        resource_name = node.resource
        if resource_name not in resources:
            resources[resource_name] = ResourceSummary(
                name=resource_name,
                cpu_free=0,
                cpu_total=0,
                ram_free_gb=0,
                ram_total_gb=0,
                gpu_free=0,
                gpu_total=0,
            )
        s = resources[resource_name]
        jupyter_cpu = round(node_cpu_jupyter.get(node.name, 0))
        jupyter_ram = round(node_ram_jupyter.get(node.name, 0), 1)
        jupyter_gpu = node_gpu_jupyter.get(node.name, 0)
        s.cpu_total += node.cpu_allocatable
        s.cpu_free += max(0, node.cpu_allocatable - jupyter_cpu)
        s.ram_total_gb += node.ram_allocatable_gb
        s.ram_free_gb += max(0.0, node.ram_allocatable_gb - jupyter_ram)
        s.gpu_total += node.gpu_allocatable
        s.gpu_free += max(0, node.gpu_allocatable - jupyter_gpu)

    return nodes, resources


def _parse_longhorn_nodes(json_str: str) -> dict:
    """
    Parse `kubectl get nodes.longhorn.io -n longhorn-system -o json`.

    Returns {node_name: [DiskInfo, ...]}. Returns {} on error.
    Merges spec.disks (path, allowScheduling) with status.diskStatus
    (storageMaximum, storageAvailable, storageScheduled) by disk name key.
    Skips disks where storageMaximum == 0 (not yet initialised by Longhorn).

    CRD fields map to Longhorn Prometheus metrics:
      storageMaximum   → longhorn_disk_capacity_bytes
      storageAvailable → complement of longhorn_disk_usage_bytes
      storageScheduled → longhorn_disk_reservation_bytes
    """
    _BYTES_PER_GIB = 1_073_741_824
    result: dict = {}
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return result
    for item in data.get("items", []):
        try:
            node_name = item.get("metadata", {}).get("name", "")
            if not node_name:
                continue
            spec_disks = item.get("spec", {}).get("disks", {})
            disk_status = item.get("status", {}).get("diskStatus", {})
            disks = []
            for disk_name, status in disk_status.items():
                total_bytes = status.get("storageMaximum", 0)
                if total_bytes == 0:
                    continue  # not yet initialised
                available_bytes = status.get("storageAvailable", 0)
                scheduled_bytes = status.get("storageScheduled", 0)
                spec = spec_disks.get(disk_name, {})
                path = spec.get("path", "")
                schedulable = spec.get("allowScheduling", False)
                disks.append(
                    DiskInfo(
                        name=disk_name,
                        path=path,
                        total_gb=round(total_bytes / _BYTES_PER_GIB, 1),
                        available_gb=round(available_bytes / _BYTES_PER_GIB, 1),
                        scheduled_gb=round(scheduled_bytes / _BYTES_PER_GIB, 1),
                        schedulable=schedulable,
                    )
                )
            if disks:
                result[node_name] = sorted(disks, key=lambda d: d.name)
        except Exception:
            continue
    return result
