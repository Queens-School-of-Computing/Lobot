"""Action definitions for lobot-tui."""

from dataclasses import dataclass
from typing import Callable

from ..config import (
    CONTROL_PLANE,
    JUPYTERHUB_API_URL,
    JUPYTERHUB_CHART,
    JUPYTERHUB_CHART_VERSION,
    JUPYTERHUB_NAMESPACE,
    JUPYTERHUB_RELEASE,
    REPO_DIR,
    TOOLS_DIR,
)


@dataclass
class ActionField:
    name: str
    label: str
    default: str
    required: bool = True
    placeholder: str = ""
    field_type: str = "input"
    # field_type values:
    #   "input"        — plain text Input widget
    #   "checkbox"     — Checkbox widget; default "true"/"false"; value stored as bool
    #   "tag_select"   — image-name Input + async tag Select combo
    #   "node_exclude" — text Input + "Pick…" button (multi-select, comma-sep)
    #   "node_single"  — text Input + "Pick…" button (single node, -n flag)


@dataclass
class ActionDef:
    key: str
    name: str
    description: str
    needs_confirm: bool
    has_dry_run: bool
    fields: list
    build_command: Callable
    working_dir: str = TOOLS_DIR
    confirm_message: str = ""
    docs_path: str = ""  # filename relative to working_dir; shown as "View Docs" link in confirmation


# ── Command builders ──────────────────────────────────────────────────────────


def _image_pull_cmd(values: dict) -> list:
    cmd = ["bash", "image-pull.sh", "-i", values["image"]]
    batch = values.get("batch_size", "3").strip() or "3"
    cmd += ["-b", batch]
    timeout = values.get("timeout", "1200").strip() or "1200"
    cmd += ["-t", timeout]
    node = values.get("node", "").strip()
    if node:
        cmd += ["-n", node]
    else:
        exclude = values.get("exclude", CONTROL_PLANE).strip()
        if exclude:
            cmd += ["-e", exclude]
    if values.get("use_latest"):
        cmd.append("--latest")
    cmd.append("--yes")
    if values.get("dry_run"):
        cmd.append("--dry-run")
    return cmd


def _image_cleanup_cmd(values: dict) -> list:
    cmd = ["bash", "image-cleanup.sh", "-i", values["image"]]
    node = values.get("node", "").strip()
    if node:
        cmd += ["-n", node]
    else:
        exclude = values.get("exclude", CONTROL_PLANE).strip()
        if exclude:
            cmd += ["-e", exclude]
    cmd.append("--yes")
    if values.get("dry_run"):
        cmd.append("--dry-run")
    return cmd


def _apply_config_cmd(values: dict) -> list:
    return ["bash", "apply-config.sh"]


def _sync_groups_cmd(values: dict) -> list:
    cmd = ["bash", "sync_groups.sh", JUPYTERHUB_API_URL]
    if values.get("dry_run"):
        cmd.append("--dry-run")
    return cmd


def _helm_upgrade_cmd(values: dict) -> list:
    return [
        "helm",
        "upgrade",
        "--cleanup-on-fail",
        JUPYTERHUB_RELEASE,
        JUPYTERHUB_CHART,
        "--namespace",
        JUPYTERHUB_NAMESPACE,
        "--version",
        JUPYTERHUB_CHART_VERSION,
        "--values",
        "/opt/Lobot/config.yaml",
        "--values",
        "/opt/Lobot/config-env.yaml",
        "--timeout",
        "60m",
    ]


# ── Registry ──────────────────────────────────────────────────────────────────

ACTIONS: list = [
    ActionDef(
        key="1",
        name="image-pull",
        description="Pre-pull a container image across all cluster nodes.",
        needs_confirm=True,
        has_dry_run=True,
        fields=[
            ActionField(
                "image",
                "Image",
                "queensschoolofcomputingdocker/gpu-jupyter-latest",
                placeholder="queensschoolofcomputingdocker/gpu-jupyter-latest",
                field_type="tag_select",
            ),
            ActionField("batch_size", "Batch size", "3", required=False, placeholder="3"),
            ActionField("timeout", "Timeout (seconds)", "1200", required=False, placeholder="1200"),
            ActionField(
                "exclude", "Exclude nodes", CONTROL_PLANE, required=False, field_type="node_exclude"
            ),
            ActionField(
                "node", "Single target node (-n)", "", required=False, field_type="node_single"
            ),
            ActionField(
                "use_latest", "Use --latest", "true", required=False, field_type="checkbox"
            ),
        ],
        build_command=_image_pull_cmd,
        working_dir=TOOLS_DIR,
        confirm_message="This will pull a large image (~18GB) across ALL nodes. Use --dry-run first.",
        docs_path="IMAGE-MANAGEMENT.md",
    ),
    ActionDef(
        key="2",
        name="image-cleanup",
        description="Remove old image tags from nodes (keeps the specified tag).",
        needs_confirm=True,
        has_dry_run=True,
        fields=[
            ActionField(
                "image",
                "Image to KEEP",
                "queensschoolofcomputingdocker/gpu-jupyter-latest",
                placeholder="queensschoolofcomputingdocker/gpu-jupyter-latest",
                field_type="tag_select",
            ),
            ActionField(
                "exclude", "Exclude nodes", CONTROL_PLANE, required=False, field_type="node_exclude"
            ),
            ActionField(
                "node", "Single target node (-n)", "", required=False, field_type="node_single"
            ),
        ],
        build_command=_image_cleanup_cmd,
        working_dir=TOOLS_DIR,
        confirm_message="This will REMOVE old image tags from nodes. Verify the keep-tag is correct.",
        docs_path="IMAGE-MANAGEMENT.md",
    ),
    ActionDef(
        key="3",
        name="apply-config",
        description="Pull JupyterHub config from GitHub and apply it to the cluster.",
        needs_confirm=True,
        has_dry_run=False,
        fields=[],
        build_command=_apply_config_cmd,
        working_dir=TOOLS_DIR,
        confirm_message=(
            "WARNING: This is a destructive cluster operation.\n\n"
            "apply-config.sh will:\n"
            "  • Pull config from GitHub (overwriting local state)\n"
            "  • Substitute secrets into the config template\n"
            "  • Overwrite /opt/Lobot/config.yaml and config-env.yaml\n\n"
            "Do NOT run this unless you have reviewed the config changes.\n"
            "Run [5] hub upgrade & restart afterwards to apply to the cluster.\n"
            "Review the documentation first."
        ),
        docs_path="apply-config.md",
    ),
    ActionDef(
        key="4",
        name="sync-groups",
        description="Sync JupyterHub group membership from group-roles.yaml.",
        needs_confirm=True,
        has_dry_run=True,
        fields=[],
        build_command=_sync_groups_cmd,
        working_dir=TOOLS_DIR,
        confirm_message="This will modify JupyterHub group memberships.",
        docs_path="sync_groups.md",
    ),
    ActionDef(
        key="5",
        name="hub-upgrade",
        description="Run helm upgrade to apply config and restart JupyterHub.",
        needs_confirm=True,
        has_dry_run=False,
        fields=[],
        build_command=_helm_upgrade_cmd,
        working_dir=REPO_DIR,
        confirm_message=(
            f"This will run: helm upgrade --cleanup-on-fail {JUPYTERHUB_RELEASE} {JUPYTERHUB_CHART}"
            f" --version {JUPYTERHUB_CHART_VERSION}\n"
            "The Hub pod will restart. Active user sessions may be briefly interrupted."
        ),
    ),
]

ACTIONS_BY_KEY = {a.key: a for a in ACTIONS}
