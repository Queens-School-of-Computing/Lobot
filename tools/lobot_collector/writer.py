"""Writes current.json atomically in the legacy format for nginx/web dashboards."""

import json
import logging
from datetime import datetime
from pathlib import Path

from lobot_tui.data.models import ClusterState

from .config import OUTPUT_FILE, RESOURCE_DISPLAY_NAMES

logger = logging.getLogger(__name__)


def write_current_json(state: ClusterState) -> None:
    """Render ClusterState as the legacy JSON format and write atomically."""
    data: dict = {}
    current_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Build per-resource pod usage strings (jupyter user pods only, not hub/proxy/etc.)
    pod_usage_by_resource: dict = {}
    for pod in state.pods:
        if not pod.resource or not pod.name.startswith("jupyter-"):
            continue
        cpu_disp = int(pod.cpu_requested) if pod.cpu_requested == int(pod.cpu_requested) else pod.cpu_requested
        ram_disp = int(pod.ram_requested_gb) if pod.ram_requested_gb == int(pod.ram_requested_gb) else f"{round(pod.ram_requested_gb * 1024)}M"
        entry = f"{pod.username} == {cpu_disp} cores, {ram_disp} mem, {pod.gpu_requested} gpu"
        pod_usage_by_resource.setdefault(pod.resource, []).append(entry)

    for resource_key, resource in state.resources.items():
        display_name = RESOURCE_DISPLAY_NAMES.get(resource_key, resource_key)
        cpu_free = int(resource.cpu_free)
        cpu_total = int(resource.cpu_total)
        ram_free = int(resource.ram_free_gb)
        ram_total = int(resource.ram_total_gb)
        gpu_free = int(resource.gpu_free)
        gpu_total = int(resource.gpu_total)

        summary = (
            f"{display_name} available resources CPU Cores: {cpu_free} of {cpu_total}, "
            f"MEMORY GB: {ram_free} of {ram_total}, GPU: {gpu_free} of {gpu_total} [{current_dt}]"
        )
        summary_title = f"{display_name} available resources as of {current_dt}"
        summary_details = (
            f"CPU Cores: {cpu_free} of {cpu_total}, "
            f"MEMORY GB: {ram_free} of {ram_total}, "
            f"GPU: {gpu_free} of {gpu_total}"
        )

        usage = list(pod_usage_by_resource.get(resource_key, []))
        usage.append(
            "NOTICE: If you select more resources than are available, "
            "your workload will be pending until resources are available."
        )

        data[resource_key] = {
            "time": current_dt,
            "summary": summary,
            "summary_title": summary_title,
            "summary_details": summary_details,
            "usage": usage,
        }

    # Atomic write: tmp → rename (prevents partial reads by nginx)
    tmp_path = Path(str(OUTPUT_FILE) + ".tmp")
    try:
        tmp_path.write_text(json.dumps(data), encoding="utf-8")
        tmp_path.rename(OUTPUT_FILE)
        logger.debug("Wrote %s", OUTPUT_FILE)
    except Exception as exc:
        logger.error("Failed to write %s: %s", OUTPUT_FILE, exc)
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
