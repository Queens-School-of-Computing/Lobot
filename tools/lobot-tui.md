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
- Launch image-pull, image-cleanup, apply-config, sync-groups, and helm upgrade — with tag dropdowns, node pickers, live streaming output, and dry-run support
- Background job mode: long-running commands (e.g. image-pull) run in the background so the dashboard remains usable during a pull
- Edit `announcement.yaml` and push directly to GitHub from within the TUI
- Clickable hint bar — every keyboard shortcut shown at the bottom is also clickable

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
┌─ LOBOT  lobot-dev.cs.queensu.ca ─────────────────── 2026-03-15 14:22:05 ─┐
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
│ NODES:[c]cordon [u]uncordon [w]drain  TOOLS:[1-6] [`]console [b]jobs …    │
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
| Actions hint bar | Bottom-2 | Dynamic — all hints clickable; replaced by job status when a job is running |
| Status bar | Bottom-1 | Live |

The **status bar** shows a green `● Live` indicator when data is fresh. If allocation data is stale by more than 15 seconds (e.g. kubectl-view-allocations is slow or failing) it shows `⚠ Stale` in amber. Errors are shown in red.

---

## Key Bindings

### Global

| Key | Action |
|-----|--------|
| `q` | Quit (press twice within 2 seconds to confirm) |
| `r` | Force-refresh all data immediately |
| `?` | Help screen (full key binding reference) |
| `` ` `` | Command console (recent command history and errors) |
| `b` | Background jobs panel (live output of running tool) |
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

### Background Jobs Panel (`b`)

The available keys depend on whether the job is still running:

**While running:**

| Key | Action |
|-----|--------|
| `b` | Background the panel — return to dashboard, job keeps running |
| `k` | Kill job — press twice within 3 seconds to confirm |
| `s` | Save output so far to `/tmp/lobot-tui-<name>-<timestamp>.log` |

> `Escape` and `q` have **no effect** while a job is running. `b` is the only navigation key, making it impossible to accidentally close the panel in a way that could be mistaken for cancellation.

**When finished (done or failed):**

| Key | Action |
|-----|--------|
| `Escape` / `q` / `b` | Close the panel and return to dashboard |
| `s` | Save full output to `/tmp/lobot-tui-<name>-<timestamp>.log` |

### Logs / Action Screens

These are used for short-lived kubectl commands (pod logs, describe, cordon, drain, etc.) — not for tool actions 1–5, which use the background jobs panel.

| Key | Action |
|-----|--------|
| `Escape` / `q` | Return to main dashboard |
| `s` | Save output to `/tmp/lobot-tui-<name>-<timestamp>.log` |
| Scroll up | **(Log viewer only)** Pause the live stream |
| `l` | **(Log viewer only)** Resume stream — flushes buffered lines and scrolls to bottom |

> **Known quirk — Escape requires two presses**: Due to how Textual's `RichLog` widget handles keyboard focus internally, pressing `Escape` in log/describe screens requires **two presses** to return to the dashboard. `q` works with a single press. This is a known limitation with no clean fix in the current Textual version.

> **Log scroll/pause**: When you scroll up in the log viewer the live stream is paused — new lines are buffered but not displayed, so your scroll position is stable. The footer changes to **⏸ Paused** and shows the `[l]` key to resume. Resuming flushes all buffered lines and jumps to the bottom. All lines (including buffered ones) are always included when you save with `s`.

---

## Tool Actions (Keys `1` – `6`)

All tool actions open a wizard screen to configure parameters before running. Press `Enter` (when not in a text field) or click **Run ↵** to submit. Tool actions (1–5) run as **background jobs** — the job starts and the output panel opens automatically. Press `b` to return to the dashboard; the job continues in the background. The tool hint bar is replaced by a live status indicator while any job is running, and pressing `1`–`5` is blocked until the job completes.

### `[1]` image-pull

Pre-pulls a container image across all cluster nodes in controlled batches. This is one of the longest-running operations (~30–60 min for an 18 GB image), so background mode is essential.

**Wizard fields:**

| Field | Type | Description | Default |
|-------|------|-------------|---------|
| Image | Text + tag dropdown | DockerHub repository name | `queensschoolofcomputingdocker/gpu-jupyter-latest` |
| Tag | Dropdown | Available tags fetched live from DockerHub, newest first | — |
| Use latest tag (`--latest`) | Checkbox | Pull the most recently pushed tag; selecting a tag from the dropdown unchecks this automatically | ✓ (checked) |
| Batch size | Text | Nodes pulling simultaneously | `3` |
| Timeout (seconds) | Text | Per-node timeout | `1200` |
| Exclude nodes | Multi-select | Worker nodes to skip (control plane always excluded by the script) | none |
| Single target node (`-n`) | Dropdown | Target one specific node (includes control plane — useful for updating it explicitly); overrides exclude list | All nodes |
| Dry run | Checkbox | Preview without pulling | ✓ (checked) |

> **Tag dropdown**: tags are loaded asynchronously from DockerHub when the wizard opens, sorted newest-first by the `YYYYMMDD` date code embedded in the tag name. If `Use latest tag` is checked, the dropdown is greyed out and `--latest` is passed to the script. Selecting a tag automatically unchecks `Use latest tag`.

> **Node fields**: `Single target node` and `Exclude nodes` are mutually exclusive in the script — if a single node is selected, the exclude list is ignored.

Generated command example:
```bash
bash image-pull.sh -i queensschoolofcomputingdocker/gpu-jupyter-latest \
  -b 3 -t 1200 -e lobot-dev.cs.queensu.ca --latest --yes
```

Or, with a specific tag and target node:
```bash
bash image-pull.sh -i queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn-20260313 \
  -b 3 -t 1200 -n gpu3 --yes
```

### `[2]` image-cleanup

Removes old image tags from all nodes while protecting images in use by running pods. The tag to **keep** is selected from a DockerHub dropdown.

**Wizard fields:**

| Field | Type | Description | Default |
|-------|------|-------------|---------|
| Image to KEEP | Text + tag dropdown | Tag to retain; all others removed | `queensschoolofcomputingdocker/gpu-jupyter-latest` |
| Tag | Dropdown | Available tags from DockerHub, newest first | — |
| Exclude nodes | Multi-select | Worker nodes to skip | none |
| Single target node (`-n`) | Dropdown | Target one specific node (includes control plane) | All nodes |
| Dry run | Checkbox | Preview without removing | ✓ (checked) |

Generated command example:
```bash
bash image-cleanup.sh \
  -i queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn-20260313 \
  -e lobot-dev.cs.queensu.ca --yes
```

### `[3]` apply-config

Pulls the JupyterHub Helm config template from the `newcluster` GitHub branch, substitutes secrets from the existing config, and applies it. Runs `sudo bash apply-config.sh` on the control plane. The Hub pod restarts briefly.

No wizard fields — a confirmation prompt is shown before the command runs.

### `[4]` sync-groups

Syncs JupyterHub group membership from `group-roles.yaml`. Runs `bash sync_groups.sh`. Supports dry-run (checkbox in wizard) to preview changes without applying them.

### `[5]` helm upgrade

Runs a full JupyterHub Helm upgrade. A **command preview screen** is shown first, displaying the exact command that will run, before any confirmation is accepted. The Hub pod restarts; active user sessions may be briefly interrupted.

```bash
helm upgrade --cleanup-on-fail jhub jupyterhub/jupyterhub \
  --namespace jhub \
  --version 4.0.0-beta.2 \
  --values /opt/Lobot/config.yaml \
  --values /opt/Lobot/config-env.yaml \
  --timeout 60m
```

> The preview screen requires an explicit confirmation (`y` or the Run button) before executing. Press `Escape` to cancel.

### `[6]` Announcement Editor

Opens a modal form with two text fields — one for the production announcement and one for the dev announcement. Current values are fetched live from GitHub (`LOBOT_ANNOUNCEMENT_URL` in the active env config) so the form always reflects the authoritative version, not a potentially stale local copy. Falls back to the local `/opt/Lobot/announcement.yaml` if GitHub is unreachable.

| Field | YAML key | Served to |
|-------|----------|-----------|
| Production | `announcement_prod` | Production JupyterHub |
| Development | `announcement_dev` | Dev JupyterHub |

| Key | Action |
|-----|--------|
| `Ctrl+S` | Save, commit, and push to GitHub (`newcluster` branch) |
| `Escape` | Cancel without saving |

On save, the TUI writes the two field values back to `announcement.yaml` and runs:
```bash
git add /opt/Lobot/announcement.yaml
git commit -m "chore: update announcement via lobot-tui"
git push origin newcluster
```

The JupyterHub announcement banner updates within seconds as the hub fetches the new YAML from GitHub.

---

## Background Job System

Tool actions 1–5 run as background jobs so the main dashboard remains usable during long operations like image-pull.

**Workflow:**
1. Press `1`–`5`, fill in the wizard, and click **Run**.
2. The background jobs panel opens immediately, showing live streaming output.
3. Press `b` to background the panel and return to the dashboard — **the job keeps running**.
4. While a job is active, the tool hint bar on the dashboard is replaced by a live status line showing the job name, elapsed time (`● image-pull  1m42s  [b] view output`). Pressing any tool key (`1`–`5`) shows a warning instead of opening a wizard.
5. Press `b` again at any time to return to the live output.
6. When the job finishes, a toast notification appears on the main dashboard showing success or failure, and the normal tool hint bar is restored.

**Safety rules:**
- **Only one tool job runs at a time.** Pressing `1`–`5` while a job is active shows a warning naming the running job. The wizard does not open.
- **`Escape` and `q` do nothing while a job is running** — they cannot accidentally dismiss the panel mid-run. Once the job finishes they work normally to close the panel.
- **Killing a job requires double confirmation.** Press `k` once to arm (footer turns red with a 3-second countdown), then `k` again to confirm SIGTERM. Waiting lets the countdown expire with no effect.
- **The indicator clears automatically** when a job completes, even if a different screen (pod logs, describe) is in the foreground — the main screen always receives the completion event.

**Jobs panel keys** — see the [Background Jobs Panel](#background-jobs-panel-b) key binding section above.

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
| Available image tags | DockerHub API (on wizard open) | On demand |
| Node list (for pickers) | `kubectl get nodes` (on wizard open) | On demand |

All subprocess calls are async — the UI never blocks waiting for `kubectl`.

---

## Audit Log

Every command executed by the TUI is automatically recorded to a daily log file — no action required from the operator.

**Location:** `/opt/Lobot/logs/lobot-tui-YYYY-MM-DD.log`

The directory is created on first use. The file rotates at midnight (a new file is started each calendar day).

Each entry records the timestamp, exit code, and full command:

```
[2026-03-15 14:22:05] [exit 0] $ kubectl describe pod jupyter-alice -n jhub
[2026-03-15 14:22:10] [exit 0] $ kubectl cordon newcluster-gpu1
[2026-03-15 14:22:15] [exit 0] $ kubectl logs -f jupyter-alice -n jhub --tail 500
[2026-03-15 14:22:30] [exit 0] $ bash image-pull.sh -i queensschoolofcomputingdocker/gpu-jupyter-latest -b 3 -t 1200 --latest --yes
[2026-03-15 14:22:35] [exit 0] $ git push origin newcluster
```

**Commands logged:**

| Action | Command logged |
|--------|---------------|
| Pod describe | `kubectl describe pod <name> -n <ns>` |
| Pod logs | `kubectl logs -f <name> -n <ns> --tail 500` |
| Pod exec | `kubectl exec -it <name> -n <ns> -- /bin/bash` |
| Pod delete | `kubectl delete pod <name> -n <ns>` |
| Node cordon | `kubectl cordon <node>` |
| Node uncordon | `kubectl uncordon <node>` |
| Node drain | `kubectl drain <node> --ignore-daemonsets --delete-emptydir-data` |
| Tool actions (1–5) | Full shell command with all arguments |
| Announcement push | Each `git add` / `git commit` / `git push` |

The in-session history is also viewable live via the console screen (`` ` ``), which shows the most recent commands first and displays the path to today's log file in the header.

### Manual save (optional)

Action and log screens can also save their full streaming output to `/tmp/` by pressing `s`:

| Screen | Filename pattern |
|--------|-----------------|
| Pod logs | `/tmp/lobot-tui-logs-<username>-<timestamp>.log` |
| Tool output (background jobs) | `/tmp/lobot-tui-<action-name>-<timestamp>.log` |

---

## Source Files

```
tools/lobot_tui/
  __main__.py               Entry point (python3 -m lobot_tui)
  app.py                    Root Textual App class; owns job_manager
  config.py                 Cluster constants and paths
  requirements-tui.txt      Python dependencies (textual, aiofiles)
  data/
    models.py               Dataclasses: PodInfo, NodeInfo, LabSummary, ClusterState
    collector.py            Async kubectl polling, ClusterStateUpdated message
    command_log.py          In-session command history (also written to audit log)
    job_manager.py          BackgroundJobManager — runs tool commands as background tasks
  screens/
    main_screen.py          Primary dashboard layout and all key bindings
    logs_screen.py          Pod log viewer
    action_screen.py        Streaming tool output screen (kubectl commands, auto-close option)
    pod_detail_screen.py    kubectl describe viewer
    action_wizard_screen.py Tool parameter input form (tag dropdowns, node pickers, dry-run)
    jobs_screen.py          Live background-job output panel (toggled with b)
    command_preview_screen.py  Pre-run command preview for destructive actions (helm upgrade)
    announcement_screen.py  YAML editor + git push
    help_screen.py          Key binding reference
    console_screen.py       Command history / debug console
    exec_screen.py          TTY handoff for kubectl exec
  widgets/
    cluster_summary.py      Per-lab resource bars
    pod_table.py            Pod DataTable with filter and column sort
    node_table.py           Node DataTable with column sort
    actions_panel.py        Key hint bar (all hints are clickable)
    status_bar.py           Bottom status line
  actions/
    definitions.py          ActionDef registry (image-pull, cleanup, apply-config, etc.)
  utils/
    tag_fetcher.py          DockerHub tag fetching; kubectl node list
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
