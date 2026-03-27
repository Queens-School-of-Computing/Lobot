"""Constants for lobot-tui."""

import os
import socket
from pathlib import Path

# ── Environment detection (matches apply-config.sh logic) ─────────────────────
_HOSTNAME = socket.getfqdn()
IS_DEV = "lobot-dev" in _HOSTNAME

# The control plane is this machine — excluded from cordon/drain/image operations
CONTROL_PLANE = _HOSTNAME

# JupyterHub public URL — used by sync_groups.sh for API calls
JUPYTERHUB_URL = f"https://{_HOSTNAME}"
JUPYTERHUB_API_URL = f"{JUPYTERHUB_URL}/hub/api"

# ── Cluster infrastructure ─────────────────────────────────────────────────────
# LOBOT_CLUSTER_DIR: path to the cluster-config repo (default: /opt/Lobot)
# LOBOT_TOOLS_DIR:   path to the tools directory (default: <LOBOT_CLUSTER_DIR>/tools)
# Set these when deploying on a cluster that isn't Queens — the Queens server
# never needs to set them since /opt/Lobot is the default.
REPO_DIR = Path(os.environ.get("LOBOT_CLUSTER_DIR", "/opt/Lobot"))
TOOLS_DIR = Path(os.environ.get("LOBOT_TOOLS_DIR", str(REPO_DIR / "tools")))
ANNOUNCEMENT_YAML = REPO_DIR / "announcement.yaml"

# Helm: base config is the same on both; env config differs
HELM_CONFIG = REPO_DIR / "config.yaml.bk"
HELM_CONFIG_ENV = REPO_DIR / ("config-dev.yaml.bk" if IS_DEV else "config-prod.yaml.bk")

# Live output files written by apply-config.sh (reviewed after running action 3)
HELM_CONFIG_LIVE = REPO_DIR / "config.yaml"
HELM_CONFIG_ENV_LIVE = REPO_DIR / "config-env.yaml"

JUPYTERHUB_NAMESPACE = "jhub"
JUPYTERHUB_RELEASE = "jhub"
JUPYTERHUB_CHART = "jupyterhub/jupyterhub"
JUPYTERHUB_CHART_VERSION = "4.0.0-beta.2"

# ── Refresh intervals (seconds) ────────────────────────────────────────────────
PODS_INTERVAL = 5
NODES_INTERVAL = 10
LONGHORN_INTERVAL = 30
LONGHORN_NAMESPACE = "longhorn-system"

# ── Display ───────────────────────────────────────────────────────────────────
APP_TITLE = "LOBOT"
MAX_TAG_LEN = 66  # truncate image tags in table (left-truncated, keeps date suffix)

# ── Dev/local mode: use mock data when kubectl is unavailable ──────────────────
DEV_MODE = os.environ.get("LOBOT_TUI_DEV", "0") == "1"

# ── Per-namespace filter persistence ──────────────────────────────────────────
NS_FILTERS_FILE = Path.home() / ".config" / "lobot-tui" / "ns_filters.json"
THEME_FILE = Path.home() / ".config" / "lobot-tui" / "theme.txt"

# ── Audit log ─────────────────────────────────────────────────────────────────
# All commands run via the TUI are appended here (rotates daily).
LOG_DIR = REPO_DIR / "logs"

# ── Safety lock: when True, tool actions 1-5 are restricted to dry-run only ───
# Set to False when ready to run tools live.
TOOLS_LOCKED = False

# ── lobot-collector service connection ────────────────────────────────────────
# The TUI connects here to receive pushed ClusterState updates via SSE.
# Falls back to direct kubectl polling if the service is not available.
SERVICE_HOST = "127.0.0.1"
SERVICE_PORT = 9095
