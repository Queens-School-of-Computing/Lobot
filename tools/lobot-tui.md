# lobot-tui — Cluster Management TUI

## Overview

A [btop](https://github.com/aristocratos/btop)-style terminal dashboard for managing the Lobot JupyterHub cluster. Provides real-time visibility into running pods, node status, and resource group allocation — along with keyboard-driven access to all common admin operations.

Designed for the control plane where a terminal is always available, including during disaster recovery when a web interface may not be.

**Capabilities at a glance:**

- Real-time pod list with resource usage, image tag, resource group, node, age, and phase
- Per-resource-group utilisation table (CPU, RAM, GPU) showing jupyter-* workload only, updated every 5 seconds
- Per-node allocation table with CPU, RAM, GPU, and Longhorn disk usage — cordon/schedulable status
- Expandable per-disk sub-rows in the node table showing individual Longhorn disk detail
- Stream pod logs, exec bash into a pod, describe or delete pods
- Cordon, uncordon, and drain nodes (double-keypress to confirm)
- Launch image-pull, image-cleanup, apply-config, sync-groups, and hub upgrade & restart — with tag dropdowns, node pickers, live streaming output, and dry-run support
- Background job mode: long-running commands (e.g. image-pull) run in the background so the dashboard remains usable during a pull
- Edit `announcement.yaml` and push directly to GitHub from within the TUI
- Clickable hint bar — every keyboard shortcut shown at the bottom is also clickable

---

## Prerequisites

- Python 3.8+ on the control plane (Ubuntu 24.04 ships Python 3.12)
- `kubectl` configured with cluster access
- `python3.12-venv` apt package (not installed by default on Ubuntu 24.04):

```bash
sudo apt install python3.12-venv
```

- Textual and aiofiles Python packages (installed into a venv — Ubuntu 24.04 enforces PEP 668):

```bash
python3 -m venv /opt/Lobot/tools/lobot_tui/.venv
/opt/Lobot/tools/lobot_tui/.venv/bin/pip install textual aiofiles
```

- `helm` on PATH (required only for the hub upgrade & restart action)
- `git` on PATH with push access to the Lobot repo (required only for the announcement editor)

---

## Installation

### lobot-tui

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

### lobot-collector service

The lobot-collector service polls kubectl once on behalf of all consumers, writes `current.json` for the web dashboards, and serves a live HTTP API on `127.0.0.1:9095` for lobot-tui.

```bash
# Create a venv for the collector (separate from the TUI venv — no Textual needed)
python3 -m venv /opt/Lobot/tools/lobot_collector/.venv
/opt/Lobot/tools/lobot_collector/.venv/bin/pip install \
  -r /opt/Lobot/tools/lobot_collector/requirements-collector.txt

# Make the launcher executable
chmod +x /opt/Lobot/tools/lobot-collector.sh

# Install and start the systemd service
sudo cp /opt/Lobot/tools/lobot-collector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lobot-collector

# Verify it is running
sudo systemctl status lobot-collector

# Follow logs
sudo journalctl -u lobot-collector -f

# Verify the HTTP API (should return ClusterState JSON)
curl -s http://localhost:9095/api/state | python3 -m json.tool
```

lobot-tui reads exclusively from this service (`svc` tag always shown in the status bar). If the service is not running, lobot-tui displays an error in the status bar with the command to start it — there is no kubectl fallback.

**Deploying updates to the collector:**

> **Important:** `parsers.py` lives inside `lobot_tui/data/` and is imported by the collector service. When updating the service, always push **both** directories:

```bash
# Push lobot_tui (contains parsers.py, shared with the collector)
rsync -avz --exclude '__pycache__' --exclude '*.pyc' --exclude '.venv' \
  /opt/Lobot/tools/lobot_tui/ PROD_HOST:/opt/Lobot/tools/lobot_tui/

# Push collector
rsync -avz --exclude '__pycache__' --exclude '*.pyc' --exclude '.venv' \
  /opt/Lobot/tools/lobot_collector/ PROD_HOST:/opt/Lobot/tools/lobot_collector/

ssh PROD_HOST "sudo systemctl restart lobot-collector"
```

---

## Deploying Updates

To push the latest code from the dev control plane to prod in one command:

```bash
# Push TUI (always push this — parsers.py is here and shared with the collector)
rsync -avz --exclude '__pycache__' --exclude '*.pyc' --exclude '.venv' \
  /opt/Lobot/tools/lobot_tui/ PROD_HOST:/opt/Lobot/tools/lobot_tui/

# Push collector (then restart the service)
rsync -avz --exclude '__pycache__' --exclude '*.pyc' --exclude '.venv' \
  /opt/Lobot/tools/lobot_collector/ PROD_HOST:/opt/Lobot/tools/lobot_collector/
ssh PROD_HOST "sudo systemctl restart lobot-collector"
```

Replace `PROD_HOST` with the production control plane hostname.

**First-time setup on prod** (if the venv doesn't exist yet):

```bash
ssh PROD_HOST "python3 -m venv /opt/Lobot/tools/lobot_tui/.venv && \
  /opt/Lobot/tools/lobot_tui/.venv/bin/pip install -q textual aiofiles"

ssh PROD_HOST "python3 -m venv /opt/Lobot/tools/lobot_collector/.venv && \
  /opt/Lobot/tools/lobot_collector/.venv/bin/pip install -q aiohttp"
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
┌─ LOBOT  lobot.cs.queensu.ca ─────────────────────── 2026-03-16 12:29:36 ─┐
│ RESOURCE        #   CPU       RAM          GPU  │ NODE       RESOURCE  …  │
│ lobot_a40       3   26/256  384/2014G      3/8  │▶titan      riselab   …  │
│ lobot_a5000     3   56/256  448/1007G      3/8  │  └disk-1   /mnt/nvm  …  │
│ lobot_a16       0    0/24     0/125G       0/8  │  └disk-10  /mnt/dis  …  │
│ bamlab          2   86/128  896/1007G      6/8  │▶newclstr-1 lobot_a40 …  │
│ gandslab        3   47/128   176/251G      1/2  │ lobot-dev  ctrl-plane…  │
│ miblab          1  168/192  768/1007G      6/6  │                         │
│ riselab         5  168/256  640/1007G      6/7  │                         │
│ winemocollab    2   87/128  832/1007G      3/4  │                         │
├─────────────────────────────────────────────────┴───────────────────────── ┤
│ PODS  ns:jhub  (n) node  (r) resource  filter: jupyter|hub    19/27 pods  │
│ POD              RESOURCE   NODE      IMAGE TAG    CPU  RAM   GPU  AGE     │
│▶ jupyter-ali11x  miblab     pluto     13.0.2cu…   10   64G    2   3d0h    │
│  jupyter-busvp52 lobot_a40  kickstart 13.0.2cu…   16  256G    1   8d2h    │
│  hub-6b6646cb8d  digilab    floppy    4.0.0-beta…  0    0G    0   2d3h    │
├────────────────────────────────────────────────────────────────────────────┤
│ PODS: [l]logs [x]exec [d]describe [X]delete [f]filter [N]ns               │
│ NODES:[n]node filter [r]resource filter [c]cordon [u]uncordon [w]drain …  │
├────────────────────────────────────────────────────────────────────────────┤
│ ● Live svc  Pods:12:29:30  Nodes:12:29:30  Disk:12:29:00  [q]quit [R]…   │
└────────────────────────────────────────────────────────────────────────────┘
```

**Panels:**

| Panel | Location | Refresh |
|-------|----------|---------|
| Resources | Top-left | 5s — one row per resource group; stats reflect jupyter-\* pods only |
| Nodes | Top-right | 5s (pods/nodes); 30s (Longhorn disk) |
| Pods | Centre | 5s |
| Actions hint bar | Bottom-2 | Dynamic — all hints clickable; replaced by job status when a job is running |
| Status bar | Bottom-1 | Live |

**Panel focus:** The active panel is highlighted with an amber border. Press `Tab` to cycle focus between the three data panels (Resources → Nodes → Pods).

The **status bar** shows an animated Braille spinner (`⠋⠙⠹…`) next to `● Live svc` when data is fresh. The spinner stops and is replaced by `⚠ Stale` (amber) when data is old. When lobot-collector is unreachable, the bar shows `✗ lobot-collector is not running` (red) with an actionable hint: `→ sudo systemctl start lobot-collector`. If the collector is running but reporting an error, it shows the error and suggests `→ sudo journalctl -u lobot-collector -n 20`. The source tag is always `svc` (cyan) — lobot-tui reads exclusively from lobot-collector. Timestamps at the bottom show last successful update times for each data type: `Pods:HH:MM:SS  Nodes:HH:MM:SS  Disk:HH:MM:SS`.

The **top bar** shows a live cluster summary: `Pods N  Nodes ready/total  GPU used/total`. The pod count reflects jupyter-* pods only (user workloads). This updates with every data refresh.

---

## Visual Design

lobot-tui uses a btop-inspired dark theme with colored progress bars and status badges throughout. All rendering helpers live in `widgets/render_utils.py`.

### Tricolour chrome

The top bar and the bottom section (actions hint bar + status bar) use a Queen's Blue (`#002452`) background. A thin horizontal stripe divides the top bar from the content area and the content area from the bottom chrome section. The stripe uses half-block Unicode characters so it occupies only half a character-cell row:

```
┌─ [Queen's Blue] LOBOT  lobot.cs.queensu.ca  ──────────────────────── ─┐
│ ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄ gold ▄▄▄▄▄▄▄▄▄▄▄▄ red ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄ │  ← thin stripe
│  … resource / node / pod panels …                                      │
│ ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀ gold ▀▀▀▀▀▀▀▀▀▀▀▀ red ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀ │  ← thin stripe
│ [Queen's Blue] PODS (l)logs …  TOOLS (1)… (q)quit                     │
│ [Queen's Blue] ● Live svc  Pods:12:29:30  Nodes:12:29:30              │
└────────────────────────────────────────────────────────────────────────┘
```

Stripe colours use exact xterm-256 palette entries so they render correctly in 256-colour SSH sessions: Queen's Gold → xterm index 214 (`#ffaf00`), Queen's Red → xterm index 124 (`#af0000`).

All chrome and stripe colours are defined as Python constants and CSS variables in `themes.py` (`CHROME`, `STRIPE_GOLD`, `STRIPE_RED`).

### Progress bars (CPU / RAM)

CPU and RAM columns display a colored block bar followed by a right-justified `used/total` value:

```
███████░░░░░░░  128/512
```

- Bar width: 7 characters. Value field: 7 characters. Total column width: 15.
- Color thresholds: green (`#008700`) below 75 %, gold (`#fabd0f`, Queen's Gold) at 75–89 %, red (`#af0000`, Queen's Red) at ≥ 90 %.
- Characters used: `▀` (U+2580 UPPER HALF BLOCK) for both filled and empty segments — the color difference distinguishes them.

### GPU bar

The GPU column uses a fixed 23-character bar where each segment represents one physical GPU, separated by `│` dividers:

```
█████│█████│░░░░░│░░░░░   2/4
```

- Each segment is `(23 − (gpu_total − 1)) ÷ gpu_total` characters wide. This gives exact integer widths for the common GPU counts 1, 2, 3, 4, 6, and 8.
- Segments with filled GPUs use bright color; unused segments use dim.
- For nodes with >23 GPUs (e.g. time-sliced 96-GPU nodes), ratio mode is used instead of segments. A minimum of 1 filled block is always shown when at least 1 GPU is in use.
- No-GPU nodes show a dim dash.
- Total column width: 29 (23 bar + 1 space + 5 value field).

### DISK bar (node table)

The DISK column appears left of CPU and shows aggregate Longhorn disk usage across all schedulable disks on the node. It uses the same block bar style as CPU/RAM:

```
███████░░░░░░░  1.3/3.5T
```

- Bar width: 10 characters. Value field: 7 characters (e.g. `1.3/3.5T`). Total column width: 18.
- Color thresholds match CPU/RAM: green below 75 %, gold at 75–89 %, red at ≥ 90 %.
- **Worst-case coloring**: the aggregate bar's color is driven by the *most full* individual disk, not the aggregate ratio. This ensures that a nearly-full disk on a node is visible on the parent row even before expanding. The bar fill still reflects the true aggregate.
- Nodes with no Longhorn data (e.g. the control plane) show a dim `–`.

### Row tinting (node table)

Cordoned nodes receive a faint amber background tint (`#1a1500`). NotReady nodes receive a faint red tint (`#1a0505`). These tints are applied to all cells in the row using `rich.text.Text` objects with an `on <bg>` style, which preserves bar colors inside the tinted row.

### Colour centralisation

All Python-level colours (used in Rich markup strings) are defined as named constants in `themes.py` and imported from there by every widget. CSS-level colours are defined as theme variables and resolved via `$variable-name` in TCSS. Editing `themes.py` is the single place to change any colour across the entire application.

### Status badges (node table)

| Status | Badge |
|--------|-------|
| Ready and schedulable | `● Ready` (green) |
| Ready but cordoned | `◆ Cordoned` (amber) |
| NotReady | `✖ NotReady` (red) |
| Control plane | `● ctrl` (dim) |

### Phase icons (pod table)

| Phase | Icon |
|-------|------|
| Running | `● Running` (green) |
| Pending | `◌ Pending` (amber) |
| Failed | `✖ Failed` (red) |
| Succeeded | `✓ Done` (dim) |

### Row selection

Selected rows use a very light blue background (`#0a1e35`) with bold text. `cursor_foreground_priority="renderable"` is set on all DataTable widgets so that bar and badge colors in the selected row are never overridden by the cursor CSS color.

### Sparkline (resource panel)

A 3-row Sparkline widget at the bottom of the resource panel charts the total pod count over the last 60 data updates (~5 minutes at 5s refresh). This gives a quick visual of pod churn over recent time.

---

## Key Bindings

### Global

| Key | Action |
|-----|--------|
| `q` | Quit (press twice within 2 seconds to confirm) |
| `R` | Force-refresh all data immediately |
| `?` | Help screen (full key binding reference) |
| `G` | Full guide — opens `lobot-tui.md` in a scrollable viewer with table of contents |
| `C` | Config viewer — opens `/opt/Lobot/config.yaml` and `config-env.yaml` for review; press `1`/`2` to switch files |
| `T` | Cycle theme (`lobot` → `tricolour` → …) — choice persisted to `~/.config/lobot-tui/theme.txt` |
| `` ` `` | Command console (recent command history and errors) |
| `b` | Background jobs panel (live output of running tool) |
| `Tab` | Cycle focus between panels: Resources → Nodes → Pods |
| `Escape` | Return focus to pod table (when filter input is focused) |

### Pod Table

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate rows |
| `f` | Focus filter input |
| `Enter` (in filter) | Apply filter and return focus to pod table |
| `Escape` (in filter) | Return focus to pod table (filter text unchanged) |
| `l` | Stream pod logs (`kubectl logs -f --tail=500`) |
| `x` | Exec bash into pod (`kubectl exec -it … -- /bin/bash`) |
| `d` or `Enter` | Full describe (`kubectl describe pod`) |
| `X` | Delete pod — press twice within 2 seconds to confirm |
| `N` | Cycle namespace — per-namespace filters are remembered |
| Click header | Sort by column (click again to reverse) |

> **Filter**: matches against pod name, resource group, node, image tag, and phase. Supports `|` as OR — e.g. `jupyter|jhub` shows pods whose name, resource, node, image, or phase contains `jupyter` or `jhub`. The `jhub` namespace starts with `jupyter|jhub` pre-filled to show only user pods and the hub pod. Per-namespace filters are saved to `~/.config/lobot-tui/ns_filters.json` and restored on next launch.

> **Exec (`x`)**: the TUI suspends, hands the terminal fully to bash, and resumes automatically when you exit the shell (`Ctrl-D` or `exit`). Works the same as `kubectl exec -it` in a plain terminal.

> **Delete (`X`)**: press `X` once to see a toast notification confirming what will be deleted. Press `X` again within 2 seconds to execute. The command output streams briefly then the screen closes automatically.

### Node Table

Focus the node table with `Tab`. The control plane (`lobot-dev.cs.queensu.ca`) is displayed but is protected from cordon/drain operations.

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate rows (including disk sub-rows) |
| `Space` / `→` | Expand disk sub-rows for the selected node (shows per-disk detail) |
| `←` | Collapse disk sub-rows for the selected node |
| Click row | Toggle disk sub-rows (same as Space/→) |
| `n` | Toggle node pod-filter — press once to filter the pod table to the selected node, press again to clear. While active, navigating to a different node auto-updates the filter. |
| `c` | Cordon node — press twice within 2 seconds to confirm |
| `u` | Uncordon node — press twice within 2 seconds to confirm |
| `w` | Drain node — press twice within 2 seconds to confirm |
| Click header | Sort by column (click again to reverse) |

> **Disk sub-rows**: nodes with Longhorn data show a `▶` indicator. Press `Space` or `→` to expand — a sub-row appears for each disk showing its mount path, schedulable status (`Sched`/`Disab`), and a per-disk usage bar. Press `←` or `Space` again to collapse. The cursor can navigate through sub-rows; all node operations (`c`, `u`, `w`, `n`) always apply to the parent node regardless of which row is selected.

> **Node filter**: when active, the filtered node name is highlighted in bold cyan in the node table and the pod panel header shows `node:<name> (n)`. Switching namespace does **not** clear the node filter.

> **Double-keypress confirmation**: for destructive node and pod operations, the first keypress shows a toast notification ("Press [key] again to confirm: …"). The second keypress within 2 seconds executes the command. The output screen closes automatically when the command completes.

> **Drain** runs `kubectl drain --ignore-daemonsets --delete-emptydir-data`.

### Resource Table

Focus the resource table with `Tab`.

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate rows |
| `r` | Toggle resource pod-filter — press once to filter the pod table to the selected resource group, press again to clear. While active, navigating to a different resource group auto-updates the filter. |
| Click header | Sort by column (click again to reverse) |

> **Resource filter**: when active, the filtered resource name is highlighted in bold cyan in the resource table and the pod panel header shows `resource:<name> (r)`. Node and resource filters are independent and can both be active simultaneously. Switching namespace does **not** clear the resource filter.

> **Stats**: CPU, RAM, and GPU values in the resource table reflect **jupyter-\* pod requests only** — system pods are excluded. This gives a view of user workload pressure per resource group. Full node-level accounting (all pods) is visible in the node table.

### Background Jobs Panel (`b`)

The available keys depend on whether the job is still running:

**While running:**

| Key | Action |
|-----|--------|
| `b` | Background the panel — return to dashboard, job keeps running |
| `k` | Kill job — press twice within 3 seconds to confirm |
| `s` | Save output so far to `/opt/Lobot/logs/lobot-tui-<name>-<timestamp>.log` |

> `Escape` and `q` have **no effect** while a job is running. `b` is the only navigation key, making it impossible to accidentally close the panel in a way that could be mistaken for cancellation.

**When finished (done or failed):**

| Key | Action |
|-----|--------|
| `Escape` / `q` / `b` | Close the panel and return to dashboard |
| `s` | Save full output to `/opt/Lobot/logs/lobot-tui-<name>-<timestamp>.log` |
| `C` | Open config viewer — shown in footer hint after an `apply-config` job completes |

### Config Viewer (`C`)

Opens `/opt/Lobot/config.yaml` (the base Helm config) and `/opt/Lobot/config-env.yaml` (the env-specific overrides) for review. These are the files written by `apply-config.sh` and read by `helm upgrade`.

| Key | Action |
|-----|--------|
| `1` | Switch to `config.yaml` |
| `2` | Switch to `config-env.yaml` |
| `Escape` / `q` | Return to previous screen |

Files are displayed with YAML syntax highlighting. Available from the main screen at any time (`C`), and also from the jobs panel — the footer shows `[C] view config` after an `apply-config` job finishes.

### Logs / Action Screens

These are used for short-lived kubectl commands (pod logs, describe, cordon, drain, etc.) — not for tool actions 1–5, which use the background jobs panel.

| Key | Action |
|-----|--------|
| `Escape` / `q` | Return to main dashboard |
| `s` | Save output to `/opt/Lobot/logs/lobot-tui-<name>-<timestamp>.log` |
| Scroll up | **(Log viewer only)** Pause the live stream |
| `l` | **(Log viewer only)** Resume stream — flushes buffered lines and scrolls to bottom |

> **Known quirk — Escape requires two presses**: Due to how Textual's `RichLog` widget handles keyboard focus internally, pressing `Escape` in log/describe screens requires **two presses** to return to the dashboard. `q` works with a single press. This is a known limitation with no clean fix in the current Textual version.

> **Log scroll/pause**: When you scroll up in the log viewer the live stream is paused — new lines are buffered but not displayed, so your scroll position is stable. The footer changes to **⏸ Paused** and shows the `[l]` key to resume. Resuming flushes all buffered lines and jumps to the bottom. All lines (including buffered ones) are always included when you save with `s`.

---

## Themes

Press `T` to cycle through available themes. The choice is saved to `~/.config/lobot-tui/theme.txt` and restored on next launch.

| Theme | Description |
|-------|-------------|
| `lobot` | Default dark theme — GitHub-dark inspired palette |
| `tricolour` | Queen's University brand identity — blue, gold, and red |

**Tricolour chrome (both themes):**

Regardless of the active theme, the top bar and bottom section (actions + status) always use the Queen's Blue chrome with the gold/red dividing stripe. These colours are fixed to the brand identity and do not change with the theme.

| Element | Colour | Hex |
|---------|--------|-----|
| Top bar / actions / status background | Queen's Blue | `#002452` |
| Stripe — left half | Queen's Gold | `#fabd0f` |
| Stripe — right half | Queen's Red | `#af0000` (xterm-256 #124) |

**Queen's Tricolour theme colour mapping:**

| Role | Colour | Hex |
|------|--------|-----|
| Surfaces / panels | Queen's Blue | `#002452` |
| Accent, titles, links | Queen's Gold | `#fabd0f` |
| Errors, failed, delete | Queen's Red | `#b90e31` |
| Selected row highlight | Queen's Red | `#b90e31` |
| Warnings, stale | Queen's Gold | `#fabd0f` |
| Live, running, ready | Bright blue | `#4a9fd4` |
| Muted text | Light Limestone | `#b4aea8` |

**Status indicator colours (both themes):**

| State | Colour | Hex |
|-------|--------|-----|
| OK / Ready / Running / Live | Deep green | `#008700` (xterm-256 #28) |
| Warning / Cordoned / Pending / Stale | Queen's Gold | `#fabd0f` |
| Critical / NotReady / Failed / Error | Queen's Red | `#af0000` (xterm-256 #124) |

**Per-session override** — useful on shared accounts (e.g. multiple admins sharing `croot`) where the saved file is common to all:

```bash
LOBOT_TUI_THEME=tricolour lobot-tui
```

When the env var is set, `T` cycles themes for that session only and does not overwrite the shared saved file.

---

## Tool Actions (Keys `1` – `6`)

Tool actions (1–5) run as **background jobs** — the job starts and the output panel opens automatically. Press `b` to return to the dashboard; the job continues in the background. The tool hint bar is replaced by a live status indicator while any job is running, and pressing `1`–`5` is blocked until the job completes.

### Action windows

Actions that require parameters open a **wizard screen**; actions that have no parameters (apply-config, hub upgrade & restart) go directly to a **command preview screen**. All action windows share the same key conventions:

| Key | Action |
|-----|--------|
| `r` | Run / submit the action |
| `q` / `Escape` | Cancel and close |
| `Space` / `Enter` | Activate the focused button |
| `y` | Confirm (confirm dialogs only) |
| `d` | View documentation (apply-config only — opens `apply-config.md`) |

Button colours follow a consistent scheme: **Cancel** = red, **Run / OK / Confirm** = green, **View Docs** = gold. The **Cancel button has focus by default** when any action window opens — pressing `r` or tabbing to Run is an explicit deliberate action.

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

Pulls the JupyterHub Helm config template from the `newcluster` GitHub branch, substitutes secrets from the existing config, and writes the output files. Runs `bash apply-config.sh` on the control plane.

**What it does:**
- Pulls config from GitHub (overwrites local state)
- Substitutes secrets into the config template
- Overwrites `/opt/Lobot/config.yaml` and `/opt/Lobot/config-env.yaml`

**What it does NOT do:** It does not run `helm upgrade` or restart the Hub. Run `[5]` hub upgrade & restart afterwards to apply the config to the cluster.

No wizard fields — a **command preview screen** with a danger warning is shown before the command runs. Press `d` to open the full `apply-config.md` documentation without leaving the dialog. After the job completes, press `C` to review the generated config files.

### `[4]` sync-groups

Syncs JupyterHub group membership from `group-roles.yaml`. Runs `bash sync_groups.sh`. Supports dry-run (checkbox in wizard) to preview changes without applying them.

### `[5]` hub upgrade & restart

Runs a full JupyterHub Helm upgrade, applying the current config and restarting the Hub pod. A **command preview screen** is shown first, displaying the exact command that will run, before any confirmation is accepted. Login and spawn pages will be briefly unavailable during the restart.

```bash
helm upgrade --cleanup-on-fail jhub jupyterhub/jupyterhub \
  --namespace jhub \
  --version 4.0.0-beta.2 \
  --values /opt/Lobot/config.yaml \
  --values /opt/Lobot/config-env.yaml \
  --timeout 60m
```

> The preview screen requires an explicit `r` keypress or clicking Run before executing. Press `q` or `Escape` to cancel.

### `[6]` Announcement Editor

Opens a modal form with two text fields — one for the production announcement and one for the dev announcement. Current values are fetched live from GitHub (`LOBOT_ANNOUNCEMENT_URL` in the active env config) so the form always reflects the authoritative version, not a potentially stale local copy. Falls back to the local `/opt/Lobot/announcement.yaml` if GitHub is unreachable.

| Field | YAML key | Served to |
|-------|----------|-----------|
| Production | `announcement_prod` | Production JupyterHub |
| Development | `announcement_dev` | Dev JupyterHub |

| Key | Action |
|-----|--------|
| `Escape` | Cancel without saving |

> **Save & push currently disabled.** The editor opens and loads current values from GitHub for reference, but the Save button and `Ctrl+S` binding are not yet wired up. A warning label is shown in the dialog: *"⚠ Save & push coming soon — edit announcement.yaml manually for now."* The git infrastructure (add / commit / push with per-step error messages) is already implemented and will be enabled in a future update.

When implemented, save will write the two field values back to `announcement.yaml` and run:
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

The TUI reads **exclusively from lobot-collector** — it makes no direct kubectl calls of its own. It polls `GET http://127.0.0.1:9095/api/state` every 5 seconds. The status bar always shows `svc` (cyan). If the service is not running, the status bar shows `✗ lobot-collector is not running` with the command to start it; if the service has an error, it shows the error with a journalctl hint.

The lobot-collector service handles all kubectl polling and also writes `current.json` for the web dashboards — see [lobot-collector service](#lobot-collector-service) under Installation.

| Data | Collected by | Interval |
|------|-------------|----------|
| Pod list, image tags, resource requests | `kubectl get pods -n jhub -o json` (in collector) | 5s |
| Node status, labels, allocatable CPU/RAM/GPU | `kubectl get nodes -o json` (in collector) | 10s |
| Longhorn disk usage per node and disk | `kubectl get nodes.longhorn.io -n longhorn-system -o json` (in collector) | 30s |
| Available image tags | DockerHub API (on wizard open) | On demand |
| Node list (for pickers) | `kubectl get nodes` (on wizard open) | On demand |

Resource utilisation is computed by aggregating pod resource requests against node allocatable values — no third-party tools required. The resource table aggregates **jupyter-\* pod requests only** (user workloads); the node table aggregates all pods. Both use only data already present in the pod and node JSON — no additional kubectl calls.

All subprocess and network calls are async — the UI never blocks.

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
| Pod logs | `/opt/Lobot/logs/lobot-tui-logs-<username>-<timestamp>.log` |
| Tool output (background jobs) | `/opt/Lobot/logs/lobot-tui-<action-name>-<timestamp>.log` |

---

## Source Files

```
tools/lobot_tui/
  __main__.py               Entry point (python3 -m lobot_tui)
  app.py                    Root Textual App class; owns job_manager; starts ServiceCollector
  config.py                 Cluster constants and paths (SERVICE_HOST, SERVICE_PORT, LONGHORN_INTERVAL)
  themes.py                 Textual Theme definitions (lobot, tricolour) + all Python-level colour constants
  requirements-tui.txt      Python dependencies (textual, aiofiles)
  data/
    models.py               Dataclasses: PodInfo, NodeInfo, DiskInfo, ResourceSummary, ClusterState (with to_dict/from_dict)
    parsers.py              Pure kubectl parsing functions (shared with lobot_collector); includes _parse_longhorn_nodes
    collector.py            ServiceCollector (HTTP polling of /api/state), ClusterStateUpdated
    command_log.py          In-session command history (also written to audit log)
    job_manager.py          BackgroundJobManager — runs tool commands as background tasks
  screens/
    main_screen.py          Primary dashboard layout and all key bindings
    logs_screen.py          Pod log viewer
    action_screen.py        Streaming tool output screen (kubectl commands, auto-close option)
    pod_detail_screen.py    kubectl describe viewer
    action_wizard_screen.py Tool parameter input form (tag dropdowns, node pickers, dry-run)
    jobs_screen.py          Live background-job output panel (toggled with b)
    guide_screen.py         Full-screen markdown viewer (lobot-tui.md); reusable for any doc file
    config_viewer_screen.py Live config file viewer (config.yaml / config-env.yaml, toggle with 1/2)
    command_preview_screen.py  Pre-run command preview for destructive actions; supports View Docs link
    confirm_screen.py       Generic boolean confirmation modal
    node_picker_screen.py   Multi/single node selector modal used by wizard
    pod_context_menu_screen.py  Right-click / Enter context menu for pod actions
    announcement_screen.py  YAML editor + git push (save/push currently disabled)
    help_screen.py          Key binding reference
    console_screen.py       Command history / debug console
    exec_screen.py          TTY handoff for kubectl exec
  widgets/
    render_utils.py         Shared rendering helpers: colored block bars (with optional color_ratio override), GPU segment bars, status badges, row tinting
    cluster_summary.py      ResourceTableWidget — per-resource-group DataTable with filter toggle and column sort
    pod_table.py            Pod DataTable with text filter, node filter, resource filter, and column sort
    node_table.py           Node DataTable with DISK column, expandable per-disk sub-rows, column sort and node filter toggle
    actions_panel.py        Key hint bar (all hints are clickable)
    status_bar.py           Bottom status line (animated spinner, service error detection, Pods/Nodes/Disk timestamps)
    tricolour_stripe.py     One-row Queen's gold+red dividing stripe widget
  actions/
    definitions.py          ActionDef registry (image-pull, cleanup, apply-config, etc.)
  utils/
    tag_fetcher.py          DockerHub tag fetching; kubectl node list
  styles/
    app.tcss                Textual CSS dark theme
tools/lobot-tui.sh          Shell launcher (supports --dev flag)

tools/lobot_collector/      lobot-collector service (shared data collection)
  __init__.py
  __main__.py               Entry point (python3 -m lobot_collector)
  config.py                 Service constants: port, paths, email settings, resource display names, LONGHORN_INTERVAL
  collector.py              Async kubectl polling loops for pods, nodes, and Longhorn disk; maintains ClusterState; pub/sub queue
  server.py                 aiohttp HTTP server: GET /api/state, GET /api/events (SSE)
  writer.py                 Renders and writes current.json in the legacy format (atomic write)
  notifier.py               Email notifications on startup/shutdown/error (30-min cooldown)
  requirements-collector.txt  Python dependencies (aiohttp)
tools/lobot-collector.sh    Shell launcher for the service
tools/lobot-collector.service  systemd unit file
```

---

## Potential Improvements

### Slack / notification integration
Post a summary to Slack when a hub upgrade & restart or image-pull completes, particularly useful for communicating maintenance to users in active sessions.

### Multi-cluster support
Add a cluster selector to switch between prod and dev clusters, reading kubeconfig context rather than relying on the default context.

### Pod resource editing
Allow editing a running pod's resource limits (CPU/RAM/GPU) inline, applying the change via `kubectl patch`.
