# lv-manage.sh — Longhorn Volume Management

## Overview

A bash script for inspecting and expanding Longhorn persistent volumes on the Lobot JupyterHub cluster. Given a PV name, PVC name, or pod name, it displays detailed information about the volume, its replicas, disk capacity, and backup headroom — and can optionally expand the volume with safety checks.

```
tools/lv-manage.sh <pv-name|pvc-name|pod-name> [namespace] [--expand SIZE] [--yes]
```

**Key capabilities:**

- Accepts a PV name, PVC name, or pod name — automatically resolves to the underlying Longhorn volume
- Shows PVC, PV, Longhorn volume, snapshot, and replica information in one view
- Per-replica disk capacity report: total, available, scheduled, and headroom
- Worst-case headroom calculation — accounts for all volumes full + one full backup snapshot each
- Safe expansion with pre-flight checks that block the operation if any replica disk would go negative
- Interactive confirmation prompt, or `--yes` for scripted / TUI use
- Polls the Longhorn volume CRD directly for expansion status — updates within 2–3 seconds

**Requires:** `kubectl` with cluster access, `jq`

---

## Usage

```bash
# Show volume info (PV, PVC, Longhorn, snapshots, replicas, disk capacity)
lv-manage.sh <pv|pvc|pod-name> [namespace]

# Show info then expand
lv-manage.sh <pvc-name> [namespace] --expand 100G

# Expand without a confirmation prompt (for scripted use)
lv-manage.sh <pvc-name> [namespace] --expand 100G --yes
```

---

## Parameters

| Parameter | Description |
|-----------|-------------|
| `<pv\|pvc\|pod-name>` | Input identifier (required). Resolved as PV → PVC → Pod. |
| `[namespace]` | Kubernetes namespace. Optional — if omitted all namespaces are searched. |
| `--expand SIZE` | New volume size. Format: number + `M`, `G`, or `T` (e.g. `100G`, `500M`, `2T`). Must be larger than the current size. |
| `--yes` | Skip the interactive confirmation prompt. Intended for use from lobot-tui or scripted automation. |

**Size format:** `100G` = 100 GiB, `500M` = 500 MiB, `2T` = 2 TiB.

---

## Input Resolution

The script accepts three types of input and resolves them in order:

1. **PV name** (cluster-scoped) — looked up directly with `kubectl get pv`
2. **PVC name** — if not found as a PV, searched by PVC name (optionally scoped to the given namespace)
3. **Pod name** — if not found as a PVC, looked up as a pod; the pod's attached PVCs are listed and info is shown for each

If a pod has multiple PVCs, info is shown for each one. Expansion is blocked when using a pod as input if the pod has more than one PVC — specify the PVC name directly instead.

---

## Output Sections

### PVC Information

Kubernetes PersistentVolumeClaim fields: name, namespace, status, requested and actual capacity, storage class, and access mode.

### PV Information

PersistentVolume fields: name, capacity, status, reclaim policy, storage class, and CSI driver.

### Longhorn Volume

Longhorn-specific volume metadata from `volumes.longhorn.io` in the `longhorn-system` namespace:

| Field | Description |
|-------|-------------|
| Volume Name | Longhorn volume CRD name (equals the CSI volumeHandle from the PV) |
| State | `attached` / `detached` |
| Robustness | `healthy` / `degraded` / `faulted` |
| Size | Provisioned size in bytes, converted to human-readable |
| Actual Used | Amount of data actually written (from `status.actualSize`) |
| Frontend | Block device frontend type (e.g. `blockdev`) |
| Replicas | Number of configured replicas |
| Current Node | Node the volume is currently attached to (`unattached` if detached) |

### Snapshots

Lists all Longhorn snapshot CRDs for this volume. Each row shows:

| Column | Description |
|--------|-------------|
| NAME | Snapshot CRD name |
| CREATED | Snapshot creation timestamp |
| STATUS | `active` (on disk) or `removed (backup ref)` |
| SIZE | Size of the snapshot data |

**Status explanation:**

- `active` — `readyToUse: true`. The snapshot is still on disk.
- `removed (backup ref)` — `readyToUse: false`. The snapshot data has been purged from disk; the CRD is kept as a reference for the nightly backup target. These are **not** counted in the on-disk usage total.

The footer row shows **On-Disk Snapshot Usage** — the sum of sizes for `active` snapshots only.

### Replicas

One block per replica showing:

| Field | Description |
|-------|-------------|
| Disk Path | Mount path of the Longhorn data disk on the replica node |
| State | Replica state (e.g. `running`) |
| Replica Size | Provisioned replica size (equals the volume size) |
| Disk Total | Total storage capacity of the disk this replica lives on |
| Disk Available | Currently free space on the disk (filesystem level) |
| Disk Scheduled | Total storage allocated to all Longhorn replicas on this disk |

**Space calculations (per replica):**

| Line | Formula | Meaning |
|------|---------|---------|
| Other Vol. Scheduled | `Disk Scheduled − this volume size` | Space already committed to other replicas on this disk |
| Expansion Headroom | `Disk Available − Other Vol. Scheduled` | Free space available for this volume to grow into |
| Backup Reserve (this) | `this volume's actual used size` | Estimated space needed for this volume's next backup snapshot |
| Backup Reserve (others) | `sum of actual used sizes of other volumes on this disk` | Estimated space needed for other volumes' next backup snapshots |
| Safe Headroom | `Expansion Headroom − Backup Reserve (this) − Backup Reserve (others)` | Space available after reserving for all pending backups |
| **Worst-Case Headroom** | `Disk Total − (2 × Disk Scheduled)` | Headroom if every volume is 100% full and has a full backup snapshot — the key expansion gate |

> A `*** INSUFFICIENT ***` flag is printed next to any negative headroom value.

---

## Disk Capacity Lookup

Longhorn stores disk status on the node CRD (`nodes.longhorn.io`) under `status.diskStatus`, keyed by **disk name** (e.g. `default-disk-9e9d2a0bab47721a`). Replica CRDs store a `spec.diskID` UUID that does not match this key directly.

The script resolves this by:
1. Reading the replica's `spec.diskPath` (e.g. `/mnt/nvme`)
2. Looking up the Longhorn node's `spec.disks` to find the disk whose `path` matches
3. Using the resulting disk **name** to index `status.diskStatus`

---

## Expansion

### Safety Check

Before any patch is applied, the script runs `check_expansion()` for each replica:

```
Current Worst-Case Headroom = Disk Total − 2 × Disk Scheduled
New Worst-Case Headroom     = Disk Total − 2 × (Disk Scheduled + delta)
```

If **any** replica's new worst-case headroom would go negative, the expansion is **blocked**:

```
Expansion blocked: worst-case headroom would go negative on one or more replicas.
  Migrate a volume off this disk to free space, then retry.
```

### Expansion Process

When the safety check passes:

1. Prints an Expansion Plan showing current size, requested size, and delta
2. Prompts for confirmation (or auto-confirms with `--yes`)
3. Patches the PVC: `kubectl patch pvc <name> -n <namespace> -p '{"spec":{"resources":{"requests":{"storage":"<size>"}}}}'`
4. Polls `volumes.longhorn.io <name> -n longhorn-system` every 2 seconds for the `spec.size` field
5. Prints progress until `spec.size` matches the requested size — typically 2–5 seconds

> **Why poll the Longhorn CRD instead of the PVC?** The Longhorn volume `spec.size` updates within seconds of the patch being applied. The PVC `status.capacity` can take several minutes to reflect the change. Polling the Longhorn CRD provides near-instant feedback.

### Expansion Blocked Cases

| Condition | Message |
|-----------|---------|
| New size ≤ current size | `New size … must be larger than current size …` |
| Input is a pod with multiple PVCs | `Pod '…' has N PVCs. Specify the PVC name directly for expansion.` |
| Input is a bare PV (no PVC) | `Expansion requires a PVC. Cannot expand a bare PV directly.` |
| Worst-case headroom goes negative | `Expansion blocked: worst-case headroom would go negative …` |

---

## Examples

```bash
# Show info for a pod (shows info for all attached PVCs)
lv-manage.sh jupyter-alice jhub

# Show info for a specific PVC
lv-manage.sh jupyter-alice-pvc jhub

# Show info via PV name (no namespace needed)
lv-manage.sh pvc-4a3f8912-1234-abcd-ef56-000000000001

# Expand a PVC to 100 GiB (with interactive confirmation)
lv-manage.sh jupyter-alice-pvc jhub --expand 100G

# Expand without confirmation (for scripted / TUI use)
lv-manage.sh jupyter-alice-pvc jhub --expand 100G --yes

# Expand a pod's single PVC
lv-manage.sh jupyter-alice jhub --expand 100G
```

---

## Integration with lobot-tui

`lv-manage.sh` is invoked directly by lobot-tui screens:

| TUI Action | Command |
|------------|---------|
| `i` on pod (LV Info) | `lv-manage.sh <pod-name> <namespace>` |
| `E` on pod (LV Expand) | First: `lv-manage.sh <pod-name> <namespace>` (info display) |
| | Then: `lv-manage.sh <pod-name> <namespace> --expand <SIZE> --yes` |
| `[7]` LV Tool → `i` on PVC | `lv-manage.sh <pvc-name> <namespace>` |
| `[7]` LV Tool → `E` on PVC | First: `lv-manage.sh <pvc-name> <namespace>` (info display) |
| | Then: `lv-manage.sh <pvc-name> <namespace> --expand <SIZE> --yes` |

The `--yes` flag is always passed from lobot-tui — the confirmation step is handled in the TUI itself before the expansion command is run.

Output from `lv-manage.sh` is rendered via `Text.from_ansi()` so ANSI colour codes (bold, cyan, dim, red) display correctly inside the Textual `RichLog` widget.

---

## Caveats

### Snapshot sizing

Longhorn snapshot sizes represent the amount of data written since the last snapshot (a diff, not the full volume). A newly created volume with no writes may show `0 B` snapshot size even if the volume has data from before the snapshot was taken.

### Worst-case headroom assumes no migration

The worst-case headroom formula (`Total − 2 × Scheduled`) does not account for future volume migrations off this disk. If the cluster is expected to rebalance replicas, the headroom may improve without any expansion needed.

### Expansion requires an attached volume (usually)

Longhorn can expand volumes that are detached (`detached` state), but the CSI resize path that the script uses (patching the PVC) triggers a filesystem resize on the next attach. For volumes attached to a running pod, the resize is online and transparent.

### `jq` required

`jq` must be installed on the control plane. On Ubuntu: `sudo apt install jq`.
