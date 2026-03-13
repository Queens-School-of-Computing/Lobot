"""Constants for lobot-tui."""

import os

# Cluster infrastructure
CONTROL_PLANE = "lobot-dev.cs.queensu.ca"
KUBECTL_VIEW_ALLOCATIONS = "/opt/Lobot/kubectl-view-allocations"
TOOLS_DIR = "/opt/Lobot/tools"
REPO_DIR = "/opt/Lobot"
ANNOUNCEMENT_YAML = "/opt/Lobot/announcement.yaml"
HELM_CONFIG = "/opt/Lobot/config.yaml.bk"
HELM_CONFIG_PROD = "/opt/Lobot/config-prod.yaml.bk"
JUPYTERHUB_NAMESPACE = "jhub"
JUPYTERHUB_RELEASE = "jhub"
JUPYTERHUB_CHART = "jupyterhub/jupyterhub"

# Refresh intervals (seconds)
PODS_INTERVAL = 5
NODES_INTERVAL = 10
ALLOC_INTERVAL = 10

# Display
APP_TITLE = "LOBOT"
MAX_TAG_LEN = 12  # truncate image tags in table

# Dev/local mode: use mock data when kubectl is unavailable
DEV_MODE = os.environ.get("LOBOT_TUI_DEV", "0") == "1"
