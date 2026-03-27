"""Configuration for lobot-collector service."""

import os
import socket
import sys
from pathlib import Path

# ── Network ────────────────────────────────────────────────────────────────────
SERVICE_HOST = "127.0.0.1"
SERVICE_PORT = 9095

# ── Output ─────────────────────────────────────────────────────────────────────
# LOBOT_CLUSTER_DIR: path to the cluster-config repo (default: /opt/Lobot)
_CLUSTER_DIR = Path(os.environ.get("LOBOT_CLUSTER_DIR", "/opt/Lobot"))
OUTPUT_FILE = _CLUSTER_DIR / "resource_collector_data" / "current.json"

# ── Polling intervals (seconds) ────────────────────────────────────────────────
PODS_INTERVAL = 5
NODES_INTERVAL = 5
LONGHORN_INTERVAL = 30
LONGHORN_NAMESPACE = "longhorn-system"

# ── Kubernetes ─────────────────────────────────────────────────────────────────
JUPYTERHUB_NAMESPACE = "jhub"

# ── Email ──────────────────────────────────────────────────────────────────────
EMAIL_ENABLED = True
SMTP_SERVER = "innovate.cs.queensu.ca"
SMTP_PORT = 25
SMTP_USE_TLS = False
SMTP_USERNAME = None
SMTP_PASSWORD = None
FROM_EMAIL = f"{socket.getfqdn().split('.')[0]}@cs.queensu.ca"
TO_EMAIL = "aaron@cs.queensu.ca,whb1@cs.queensu.ca"

# ── Resource display name mapping ──────────────────────────────────────────────
# Maps the Kubernetes node label `lab=<key>` to the human-readable name shown
# in the web dashboard summary strings.
RESOURCE_DISPLAY_NAMES: dict = {
    "gandslab": "GOAL&SWIMS Labs",
    "lobot_a40": "Lobot [A40]",
    "lobot_a5000": "Lobot [A5000]",
    "lobot_a16": "Lobot [A16]",
    "lobot_problackwell": "Lobot [Blackwell]",
    "edemsmithbusiness": "Smith School of Business (Edem)",
}

# ── Dev mode ───────────────────────────────────────────────────────────────────
# Enable with: python3 -m lobot_collector --dev  OR  LOBOT_COLLECTOR_DEV=1
DEV_MODE = "--dev" in sys.argv or os.environ.get("LOBOT_COLLECTOR_DEV", "0") == "1"
