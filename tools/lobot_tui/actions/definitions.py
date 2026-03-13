"""Action definitions for lobot-tui."""

from dataclasses import dataclass, field
from typing import Callable, Optional

from ..config import CONTROL_PLANE, TOOLS_DIR, REPO_DIR, HELM_CONFIG, HELM_CONFIG_ENV, JUPYTERHUB_NAMESPACE, JUPYTERHUB_RELEASE, JUPYTERHUB_CHART, JUPYTERHUB_API_URL


@dataclass
class ActionField:
    name: str
    label: str
    default: str
    required: bool = True
    placeholder: str = ""


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


# ── Helper to build the dry-run variant ──────────────────────────────────────

def _image_pull_cmd(values: dict) -> list:
    cmd = ["bash", "image-pull.sh", "-i", values["image"]]
    batch = values.get("batch_size", "3").strip()
    if batch and batch != "3":
        cmd += ["-b", batch]
    exclude = values.get("exclude", CONTROL_PLANE).strip()
    if exclude:
        cmd += ["-e", exclude]
    cmd.append("--yes")
    if values.get("dry_run"):
        cmd.append("--dry-run")
    return cmd


def _image_cleanup_cmd(values: dict) -> list:
    cmd = ["bash", "image-cleanup.sh", "-i", values["image"]]
    exclude = values.get("exclude", CONTROL_PLANE).strip()
    if exclude:
        cmd += ["-e", exclude]
    cmd.append("--yes")
    if values.get("dry_run"):
        cmd.append("--dry-run")
    return cmd


def _apply_config_cmd(values: dict) -> list:
    return ["sudo", "bash", "apply-config.sh"]


def _sync_groups_cmd(values: dict) -> list:
    cmd = ["bash", "sync_groups.sh", JUPYTERHUB_API_URL]
    if values.get("dry_run"):
        cmd.append("--dry-run")
    return cmd


def _helm_upgrade_cmd(values: dict) -> list:
    return [
        "helm", "upgrade", JUPYTERHUB_RELEASE, JUPYTERHUB_CHART,
        "--namespace", JUPYTERHUB_NAMESPACE,
        "--reuse-values",
        "-f", HELM_CONFIG,
        "-f", HELM_CONFIG_ENV,
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
            ActionField("image", "Image (name:tag)", "",
                        placeholder="queensschoolofcomputingdocker/gpu-jupyter-latest:TAG"),
            ActionField("batch_size", "Batch size", "3", required=False,
                        placeholder="3"),
            ActionField("exclude", "Exclude nodes (comma-sep)", CONTROL_PLANE, required=False),
        ],
        build_command=_image_pull_cmd,
        working_dir=TOOLS_DIR,
        confirm_message="This will pull a large image (~18GB) across ALL nodes. Use --dry-run first.",
    ),
    ActionDef(
        key="2",
        name="image-cleanup",
        description="Remove old image tags from nodes (keeps the specified tag).",
        needs_confirm=True,
        has_dry_run=True,
        fields=[
            ActionField("image", "Image to KEEP (name:tag)", "",
                        placeholder="queensschoolofcomputingdocker/gpu-jupyter-latest:TAG"),
            ActionField("exclude", "Exclude nodes (comma-sep)", CONTROL_PLANE, required=False),
        ],
        build_command=_image_cleanup_cmd,
        working_dir=TOOLS_DIR,
        confirm_message="This will REMOVE old image tags from nodes. Verify the keep-tag is correct.",
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
        confirm_message="This will apply the JupyterHub Helm config. Hub will restart briefly.",
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
    ),
    ActionDef(
        key="5",
        name="helm-upgrade",
        description="Run helm upgrade for the JupyterHub release.",
        needs_confirm=True,
        has_dry_run=False,
        fields=[],
        build_command=_helm_upgrade_cmd,
        working_dir=REPO_DIR,
        confirm_message=(
            f"This will run: helm upgrade {JUPYTERHUB_RELEASE} {JUPYTERHUB_CHART}\n"
            "The Hub pod will restart. Active user sessions may be briefly interrupted."
        ),
    ),
]

ACTIONS_BY_KEY = {a.key: a for a in ACTIONS}
