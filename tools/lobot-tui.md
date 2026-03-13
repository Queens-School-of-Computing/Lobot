# lobot-tui — Cluster Management TUI

## Overview

A [btop](https://github.com/aristocratos/btop)-style terminal dashboard for managing the Lobot JupyterHub cluster. Provides real-time visibility into running pods, node status, and lab resource allocation — along with keyboard-driven access to all common admin operations.

Designed for the control plane where a terminal is always available, including during disaster recovery when a web interface may not be.

**Capabilities at a glance:**

- Real-time pod list with resource usage, image tag, lab, node, age, and phase
- Per-lab resource utilisation table (CPU, RAM, GPU) updated every 10 seconds
- Per-node allocation table with cordon/schedulable status
- Stream pod logs, exec bash into a pod, describe or delete pods
- Cordon, uncordon, and drain nodes (double-keypress to confirm)
- Launch image-pull, image-cleanup, apply-config, sync-groups, and helm upgrade — with live streaming output and dry-run support
- Edit `announcement.yaml` and push directly to GitHub from within the TUI

---

## Prerequisites

- Python 3.8+ on the control plane (Ubuntu 24.04 ships Python 3.12)
- `kubectl` configured with cluster access
- `/opt/Lobot/kubectl-view-allocations` binary present
- `python3.12-venv` apt package (not installed by default on Ubuntu 24.04):

```bash
sudo apt install python3.12-venv
```

- Textual and aiofiles Python packages (installed into a venv — Ubuntu 24.04 enforces PEP 668):

```bash
python3 -m venv /opt/Lobot/tools/lobot_tui/.venv
/opt/Lobot/tools/lobot_tui/.venv/bin/pip install textual aiofiles
```

- `helm` on PATH (required only for the helm upgrade action)
- `git` on PATH with push access to the Lobot repo (required only for the announcement editor)

---

## Installation

```bash
# Clone/pull the repo on the control plane (if not already at /opt/Lobot)
cd /opt/Lobot

# Install Python dependencies into a venv (required on Ubuntu 24.04)
python3 -m venv tools/lobot_tui/.venv
tools/lobot_tui/.venv/bin/pip install -r tools/lobot_tui/requirements-tui.txt

# Optional: symlink for quick access
ln -sf /opt/Lobot/tools/lobot-tui.sh /usr/local/bin/lobot-tui
chmod +x /opt/Lobot/tools/lobot-tui.sh
```

---

## Deploying Updates

To push the latest code from the dev control plane to prod in one command:

```bash
rsync -avz --exclude '__pycache__' --exclude '*.pyc' --exclude '.venv' \
  /opt/Lobot/tools/lobot_tui/ PROD_HOST:/opt/Lobot/tools/lobot_tui/
```

Replace `PROD_HOST` with the production control plane hostname.

**First-time setup on prod** (if the venv doesn't exist yet):

```bash
ssh PROD_HOST "python3 -m venv /opt/Lobot/tools/lobot_tui/.venv && \
  /opt/Lobot/tools/lobot_tui/.venv/bin/pip install -q textual aiofiles"
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
│ LAB             #   CPU       RAM        GPU  │ NODES                      │
│ lobot_a40       5   78/256  576/2014G    5/8  │ NAME       STATUS  CPU  …  │
│ lobot_a5000     7  142/256  704/1007G    3/8  │ gpu1       Ready  45/64 …  │
│ lobot_a16       0    2/24     0/125G     0/8  │ gpu2       Ready  12/64 …  │
│ bamlab          2   86/128  896/1007G    6/8  │ gpu3       Cordoned  …  …  │
│ gandslab        3   47/128   176/251G    1/2  │ lobot-dev  ctrl    –    –  │
│ miblab          1  168/192  768/1007G    6/6  │                            │
│ riselab         4  168/256  640/1007G    6/7  │                            │
│ winemocollab    2   87/128  832/1007G    3/4  │                            │
├───────────────────────────────────────────────┴────────────────────────────┤
│ PODS  ns:[jhub]  filter: jupyter|jhub                          43 pods     │
│ POD              LAB        NODE      IMAGE TAG    CPU  RAM   GPU  AGE     │
│▶ jupyter-ali11x  mulab      debwewin  13.0.2cu…   10   64G    2   3d0h    │
│  jupyter-busvp52 lobot_a40  kickstart 13.0.2cu…   16  256G    1   8d2h    │
│  hub-6b6646cb8d  digilab    floppy    4.0.0-beta…  0    0G    0   2d3h    │
├────────────────────────────────────────────────────────────────────────────┤
│ PODS: [l]logs [x]exec [d]describe [X]delete [/]filter [n]ns               │
│ NODES:[c]cordon [u]uncordon [w]drain  TOOLS:[1-6] [?]help [q]quit         │
├────────────────────────────────────────────────────────────────────────────┤
│ ● Live  Pods:14:22:03  Nodes:14:22:01  Alloc:14:22:01   [q]quit           │
└────────────────────────────────────────────────────────────────────────────┘
```

**Panels:**

| Panel | Location | Refresh |
|-------|----------|---------|
| Cluster Summary | Top-left | 10s (allocations) — compact table, one row per lab |
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
| `r` | Force-refresh all data immediately |
| `?` | Help screen (full key binding reference) |
| `` ` `` | Command console (recent command history and errors) |
| `Escape` | Clear filter / go back |

### Pod Table

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate rows |
| `/` | Focus filter input |
| `Enter` (in filter) | Apply filter and return focus to pod table |
| `Escape` | Clear filter and return focus to pod table |
| `l` | Stream pod logs (`kubectl logs -f --tail=500`) |
| `x` | Exec bash into pod (`kubectl exec -it … -- /bin/bash`) |
| `d` or `Enter` | Full describe (`kubectl describe pod`) |
| `X` | Delete pod — press twice within 2 seconds to confirm |
| `n` | Cycle namespace — per-namespace filters are remembered |
| Click header | Sort by column (click again to reverse) |

> **Filter**: matches against pod name, lab, node, image tag, and phase. Supports `|` as OR — e.g. `jupyter|jhub` shows pods whose name, lab, node, image, or phase contains `jupyter` or `jhub`. The `jhub` namespace starts with `jupyter|jhub` pre-filled to show only user pods and the hub pod. Per-namespace filters are saved to `~/.config/lobot-tui/ns_filters.json` and restored on next launch.

> **Exec (`x`)**: the TUI suspends, hands the terminal fully to bash, and resumes automatically when you exit the shell (`Ctrl-D` or `exit`). Works the same as `kubectl exec -it` in a plain terminal.

> **Delete (`X`)**: press `X` once to see a toast notification confirming what will be deleted. Press `X` again within 2 seconds to execute. The command output streams briefly then the screen closes automatically.

### Node Table

Focus the node table with `Tab`. The control plane (`lobot-dev.cs.queensu.ca`) is displayed but is protected from cordon/drain operations.

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate rows |
| `c` | Cordon node — press twice within 2 seconds to confirm |
| `u` | Uncordon node — press twice within 2 seconds to confirm |
| `w` | Drain node — press twice within 2 seconds to confirm |
| Click header | Sort by column (click again to reverse) |

> **Double-keypress confirmation**: for destructive node and pod operations, the first keypress shows a toast notification ("Press [key] again to confirm: …"). The second keypress within 2 seconds executes the command. The output screen closes automatically when the command completes.

> **Drain** runs `kubectl drain --ignore-daemonsets --delete-emptydir-data`.

### Logs / Action Screens

| Key | Action |
|-----|--------|
| `Escape` / `q` | Return to main dashboard |
| `s` | Save output to `/tmp/lobot-tui-<name>-<timestamp>.log` |

---

## Tool Actions (Keys `1` – `6`)

All tool actions open a wizard or editor screen.

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

Output streams live. The Hub pod restarts; active user sessions may be briefly interrupted.

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
  requirements-tui.txt      Python dependencies (textual, aiofiles)
  data/
    models.py               Dataclasses: PodInfo, NodeInfo, LabSummary, ClusterState
    collector.py            Async kubectl polling, ClusterStateUpdated message
  screens/
    main_screen.py          Primary dashboard layout and all key bindings
    logs_screen.py          Pod log viewer
    action_screen.py        Streaming tool output screen (auto-close option)
    pod_detail_screen.py    kubectl describe viewer
    action_wizard_screen.py Tool parameter input form
    announcement_screen.py  YAML editor + git push
    help_screen.py          Key binding reference
    console_screen.py       Command history / debug console
    exec_screen.py          TTY handoff for kubectl exec
  widgets/
    cluster_summary.py      Per-lab resource bars
    pod_table.py            Pod DataTable with filter and column sort
    node_table.py           Node DataTable with column sort
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
