"""Utilities for fetching available image tags from DockerHub and runtime_setting.yaml,
and for discovering cluster nodes via kubectl."""

import json
import re
import subprocess
import urllib.request

DOCKERHUB_TAGS_URL = (
    "https://hub.docker.com/v2/repositories/{}/tags/?page_size=100&ordering=-last_updated"
)

RUNTIME_SETTING_URL = (
    "https://raw.githubusercontent.com/Queens-School-of-Computing/"
    "Lobot/newcluster/runtime_setting.yaml"
)


def fetch_dockerhub_tags(image: str) -> list:
    """Return list of tag name strings for image (org/name) from DockerHub, newest first."""
    url = DOCKERHUB_TAGS_URL.format(image)
    with urllib.request.urlopen(url, timeout=10) as r:
        data = json.load(r)
    return [t["name"] for t in data.get("results", [])]


def get_worker_nodes(control_plane: str, include_control_plane: bool = False) -> list:
    """
    Return sorted list of node names from kubectl.

    By default the control plane is excluded (it is auto-excluded by the
    image-pull/cleanup scripts). Pass include_control_plane=True when the
    caller needs to explicitly target it (e.g. -n <node> single-target mode).
    """
    try:
        result = subprocess.run(
            ["kubectl", "get", "nodes", "--no-headers", "-o", "custom-columns=NAME:.metadata.name"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        nodes = sorted(n.strip() for n in result.stdout.splitlines() if n.strip())
        if not include_control_plane:
            nodes = [n for n in nodes if n != control_plane]
        return nodes
    except Exception:
        return []


def fetch_runtime_tags() -> list:
    """Return unique image:tag values from <option value="..."> in runtime_setting.yaml."""
    with urllib.request.urlopen(RUNTIME_SETTING_URL, timeout=10) as r:
        content = r.read().decode()
    # Extract all option values that contain a colon (image:tag format)
    matches = re.findall(r'<option value="([^"]+:[^"]+)"', content)
    # Deduplicate while preserving order
    seen = set()
    result = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            result.append(m)
    return result
