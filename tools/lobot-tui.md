# lobot-tui — Cluster Management TUI

## Overview

A [btop](https://github.com/aristocratos/btop)-style terminal dashboard for managing the Lobot JupyterHub cluster. Provides real-time visibility into running pods, node status, and lab resource allocation — along with keyboard-driven access to all common admin operations.

Designed for the control plane (`lobot-dev.cs.queensu.ca`) where a terminal is always available, including during disaster recovery when a web interface may not be.

**Capabilities at a glance:**

- Real-time pod list with resource usage, image tag, lab, node, age, and phase
- Per-lab resource utilisation bars (CPU, RAM, GPU) updated every 5 seconds
- Per-node allocation table with cordon/schedulable status
- Stream pod logs, exec bash into a pod, describe or delete pods
- Cordon, uncordon, and drain nodes
- Launch image-pull, image-cleanup, apply-config, sync-groups, and helm upgrade — with live streaming output and dry-run support
- Edit `announcement.yaml` and push directly to GitHub from within the TUI

---

## Prerequisites

- Python 3.8+ on the control plane (Ubuntu 24.04 ships Python 3.12)
- `kubectl` configured with cluster access
- `/opt/Lobot/kubectl-view-allocations` binary present
- Textual and aiofiles Python packages:

```bash
pip3 install textual aiofiles
```

- `helm` on PATH (required only for the helm upgrade action)
- `git` on PATH with push access to the Lobot repo (required only for the announcement editor)

---

## Installation

```bash
# Clone/pull the repo on the control plane (if not already at /opt/Lobot)
cd /opt/Lobot

# Install Python dependencies
pip3 install -r tools/lobot-tui/requirements-tui.txt

# Optional: symlink for quick access
ln -sf /opt/Lobot/tools/lobot-tui.sh /usr/local/bin/lobot-tui
chmod +x /opt/Lobot/tools/lobot-tui.sh
```

---

## Usage

```bash
# Standard launch (requires kubectl access)
bash /opt/Lobot/tools/lobot-tui.sh

# Or, if symlinked:
lobot-tui

# Dev/demo mode — mock data, no kubectl required
bash /opt/Lobot/tools/lobot-tui.sh --dev
LOBOT_TUI_DEV=1 python3 -m lobot_tui
```

The tool can also be run as a Python module directly:

```bash
cd /opt/Lobot/tools
python3 -m lobot_tui
```

---

## Dashboard Layout

```
┌─ LOBOT  lobot-dev.cs.queensu.ca ─────────────────── 2026-03-13 14:22:05 ─┐
│ CLUSTER SUMMARY               │ NODES                                      │
│ Lobot [A40]  [3 pods]         │ NAME             STATUS  CPU    RAM  GPU   │
│   CPU ████████░░ 65/256        │ newcluster-gpu1  Ready  26/64  256G  2/2  │
│   RAM █████░░░░░ 320/2014GB    │ newcluster-gpu2  Ready   8/64   64G  1/2  │
│   GPU ████████░░ 3/8           │ newcluster-gpu3  Cordoned 10/64 64G  2/2  │
│ Lobot [A5000] [3 pods]        │ lobot-dev        ctrl    –      –    –    │
│   CPU ████████░░ 103/256       │                                            │
│   GPU ████░░░░░░ 4/8           │                                            │
├───────────────────────────────┴────────────────────────────────────────────┤
│ PODS  namespace:[jhub]  filter:__________  24 pods                         │
│ USERNAME         LAB        NODE      IMAGE TAG    CPU  RAM   GPU  AGE     │
│▶ ruslanamruddin  lobot_a40  gpu-1     13.0.2cu…   10   128G   1   2d3h    │
│  busvp52         lobot_a40  gpu-1     13.0.2cu…   16   128G   1   1d1h    │
│  ryanz8          miblab     gpu-3     13.0.2cu…   64   512G   4   3d      │
├────────────────────────────────────────────────────────────────────────────┤
│ PODS: [l]logs [x]exec [d]delete [R]restart [D]describe [/]filter [n]ns    │
│ NODES:[c]cordon [u]uncordon [w]drain  TOOLS:[1-6] [?]help [q]quit         │
├────────────────────────────────────────────────────────────────────────────┤
│ ● Live  Pods:14:22:03  Nodes:14:22:01  Alloc:14:22:01   [q]quit           │
└────────────────────────────────────────────────────────────────────────────┘
```

**Panels:**

| Panel | Location | Refresh |
|-------|----------|---------|
| Cluster Summary | Top-left | 10s (allocations) |
| Nodes | Top-right | 10s |
| Pods | Centre | 5s |
| Actions hint bar | Bottom-2 | Static |
| Status bar | Bottom-1 | Live |

The **status bar** shows a green `● Live` indicator when data is fresh. If allocation data is stale by more than 15 seconds (e.g. kubectl-view-allocations is slow or failing) it shows `⚠ Stale` in amber. Errors are shown in red.

---

## Key Bindings

### Global

| Key | Action |
|-----|--------|
| `q` | Quit |
| `Tab` / `Shift+Tab` | Cycle focus between panels |
| `r` | Force-refresh all data immediately |
| `?` | Help screen (full key binding reference) |
| `1` – `6` | Open tool action wizard |
| `Escape` | Close modal or go back |

### Pod Table

Focus the pod table with `Tab`. Navigation works with arrow keys or vim-style `j`/`k`.

| Key | Action |
|-----|--------|
| `j` / `↓` | Move selection down |
| `k` / `↑` | Move selection up |
| `/` | Focus filter input (type to narrow pod list) |
| `Escape` | Clear filter |
| `l` | Stream pod logs (`kubectl logs -f --tail=500`) |
| `x` | Exec bash into pod (`kubectl exec -it … -- /bin/bash`) |
| `d` | Delete pod — confirm required |
| `R` | Restart pod — deletes pod; JupyterHub respawns on next access |
| `D` or `Enter` | Full describe (`kubectl describe pod`) |
| `n` | Cycle namespace: `jhub` → `all` → `jhub` |

> **Exec (`x`)**: the TUI suspends, hands the terminal fully to bash, and resumes automatically when you exit the shell. Works the same as `kubectl exec -it` in a plain terminal.

> **Restart (`R`)**: deletes the pod but does not prevent JupyterHub from respawning it. Use **Delete** (`d`) if you want the server to stop until the user manually starts it again.

### Node Table

Focus the node table with `Tab`. The control plane (`lobot-dev.cs.queensu.ca`) is displayed but is protected from cordon/drain operations.

| Key | Action |
|-----|--------|
| `j` / `↓` | Move selection down |
| `k` / `↑` | Move selection up |
| `c` | Cordon node — prevent new pods from scheduling |
| `u` | Uncordon node — restore scheduling |
| `w` | Drain node — evict all pods (confirm required) |

> **Drain** runs `kubectl drain --ignore-daemonsets --delete-emptydir-data`. A confirmation modal shows the full command before execution. Output streams live in an action screen.

### Logs / Action Screens

| Key | Action |
|-----|--------|
| `Escape` / `q` | Return to main dashboard |
| `s` | Save output to `/tmp/lobot-tui-<name>-<timestamp>.log` |

---

## Tool Actions (Keys `1` – `6`)

All tool actions open a wizard or editor screen. Destructive actions require confirmation before running.

### `[1]` image-pull

Pre-pulls a container image across all cluster nodes in controlled batches.

**Wizard fields:**

| Field | Description | Default |
|-------|-------------|---------|
| Image (name:tag) | Full image reference to pull | — |
| Batch size | Nodes pulling simultaneously | `3` |
| Exclude nodes | Comma-separated nodes to skip | `lobot-dev.cs.queensu.ca` |
| Dry run | Preview without pulling | ✓ (checked) |

Output streams live in an action screen. Supports `--dry-run` to check which nodes already have the image and estimate disk space before committing to the full pull.

### `[2]` image-cleanup

Removes old image tags from all nodes while protecting images in use by running pods.

**Wizard fields:**

| Field | Description | Default |
|-------|-------------|---------|
| Image to KEEP (name:tag) | Tag to retain; all others removed | — |
| Exclude nodes | Comma-separated nodes to skip | `lobot-dev.cs.queensu.ca` |
| Dry run | Preview without removing | ✓ (checked) |

### `[3]` apply-config

Pulls the JupyterHub Helm config template from the `newcluster` GitHub branch, substitutes secrets from the existing config, and applies it. Runs `sudo bash apply-config.sh` on the control plane. The Hub pod restarts briefly.

Confirm required. No dry-run mode.

### `[4]` sync-groups

Syncs JupyterHub group membership from `group-roles.yaml`. Runs `bash sync_groups.sh`. Supports dry-run to preview changes without applying them.

### `[5]` helm upgrade

Runs a full JupyterHub Helm upgrade:

```bash
helm upgrade jhub jupyterhub/jupyterhub \
  --namespace jhub \
  --reuse-values \
  -f /opt/Lobot/config.yaml.bk \
  -f /opt/Lobot/config-prod.yaml.bk
```

Confirm required. Output streams live. The Hub pod restarts; active user sessions may be briefly interrupted.

### `[6]` Announcement Editor

Opens a full-screen YAML editor loaded with the current contents of `/opt/Lobot/announcement.yaml`.

```
┌─ ANNOUNCEMENT EDITOR ────────────────── [Ctrl+S] save & push  [Esc] back ─┐
│ announcement_prod: >                                                         │
│   Mar 13 2026 - Maintenance window tonight 10pm–midnight.                  │
│ announcement_dev: >                                                          │
│   Dev announcement here.                                                    │
└────────────────────────────────────────────────────────────────────────────┘
```

| Key | Action |
|-----|--------|
| `Ctrl+S` | Save file, commit, and push to GitHub (`newcluster` branch) |
| `Escape` | Return without saving |

On save, the TUI runs:
```bash
git add /opt/Lobot/announcement.yaml
git commit -m "chore: update announcement via lobot-tui"
git push origin newcluster
```

The JupyterHub announcement banner updates within seconds as the hub fetches the new YAML from GitHub.

---

## Dev / Demo Mode

Run with `--dev` or `LOBOT_TUI_DEV=1` to launch with static mock data. No `kubectl` or cluster access required. Useful for testing on a development workstation before deploying.

```bash
bash /opt/Lobot/tools/lobot-tui.sh --dev
```

All UI panels render with representative data. Pod actions (logs, exec, delete) are wired up but will fail gracefully since there is no real cluster.

---

## Data Sources

The TUI polls `kubectl` directly — it does **not** read from `current.json`. This keeps the TUI self-contained and independent of the `resource_collector` systemd service.

| Data | Source | Interval |
|------|--------|----------|
| Pod list, image tags | `kubectl get pods -n jhub -o json` | 5s |
| Node status, labels | `kubectl get nodes --show-labels -o json` | 10s |
| CPU/RAM/GPU allocations | `/opt/Lobot/kubectl-view-allocations -o csv` | 10s |

All subprocess calls are async — the UI never blocks waiting for `kubectl`.

---

## Log Files

Action and log screens write output to `/tmp/` when you press `s`:

| Screen | Filename pattern |
|--------|-----------------|
| Pod logs | `lobot-tui-logs-<username>-<timestamp>.log` |
| Tool output | `lobot-tui-<action-name>-<timestamp>.log` |

---

## Source Files

```
tools/lobot-tui/
  __main__.py               Entry point (python3 -m lobot_tui)
  app.py                    Root Textual App class
  config.py                 Cluster constants and paths
  requirements-tui.txt      Python dependencies
  data/
    models.py               Dataclasses: PodInfo, NodeInfo, LabSummary, ClusterState
    collector.py            Async kubectl polling, ClusterStateUpdated message
  screens/
    main_screen.py          Primary dashboard layout and all key bindings
    logs_screen.py          Pod log viewer
    action_screen.py        Streaming tool output screen
    confirm_screen.py       Destructive action modal
    pod_detail_screen.py    kubectl describe viewer
    action_wizard_screen.py Tool parameter input form
    announcement_screen.py  YAML editor + git push
    help_screen.py          Key binding reference
  widgets/
    cluster_summary.py      Per-lab resource bars
    pod_table.py            Pod DataTable with filter
    node_table.py           Node DataTable
    actions_panel.py        Key hint bar
    status_bar.py           Bottom status line
  actions/
    definitions.py          ActionDef registry (image-pull, cleanup, etc.)
    runner.py               Async subprocess runner (yields lines)
  styles/
    app.tcss                Textual CSS dark theme
tools/lobot-tui.sh          Shell launcher (supports --dev flag)
```

---

## Potential Improvements

### Web dashboard
The same data model (`collector.py`, `models.py`) could back a web-based dashboard served from the control plane — providing the same live cluster view from a browser without requiring an SSH session.

### Slack / notification integration
Post a summary to Slack when a helm upgrade or image-pull completes, particularly useful for communicating maintenance to users in active sessions.

### Multi-cluster support
Add a cluster selector to switch between prod and dev clusters, reading kubeconfig context rather than relying on the default context.

### Pod resource editing
Allow editing a running pod's resource limits (CPU/RAM/GPU) inline, applying the change via `kubectl patch`.
