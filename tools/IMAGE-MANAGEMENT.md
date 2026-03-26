# Kubernetes Image Management Scripts
![Lobot Cluster Management](https://raw.githubusercontent.com/Queens-School-of-Computing/Lobot/newcluster/assets/images/cleanpullbanner.jpg)
## Overview

Two bash scripts for managing large container images across a Kubernetes cluster
running containerd. Designed for clusters where images are large (10GB+) and
network bandwidth must be carefully managed during image operations.

- **[`image-pull.sh`](https://github.com/Queens-School-of-Computing/Lobot/blob/newcluster/tools/image-pull.sh)** — Pre-pulls images across nodes in controlled batches to avoid saturating the network during helm upgrades
- **[`image-cleanup.sh`](https://github.com/Queens-School-of-Computing/Lobot/blob/newcluster/tools/image-cleanup.sh)** — Removes old image tags from all nodes while protecting images in active use by running pods

Both scripts support `--dry-run` mode for safe pre-flight checks, and send HTML
email notifications on completion via Python smtplib.

Both scripts are designed to run from the cluster control plane with `kubectl`
access and write log files automatically alongside their output.

---

## Prerequisites

- `kubectl` configured with cluster access
- Cluster nodes running containerd v2.x with `ctr` at `/usr/bin/ctr`
- Nodes must allow privileged pods with `hostPID: true` in `kube-system`
- `alpine:latest` must be pullable on all nodes (used as the lightweight pod base)
- `nsenter` available in alpine (used to access host containerd from within pods)
- Python 3 on the control plane (used for HTML email notifications via smtplib)

---

## image-pull.sh

### Purpose

Pre-pulls a new image across cluster nodes in controlled batches before a helm
upgrade. Without this, helm upgrades cause all nodes to pull simultaneously,
saturating the network and causing pod scheduling delays.

### Usage

```bash
./image-pull.sh -i <image[:tag]> [-i <image[:tag]> ...] [-b <batch_size>] [-t <timeout>] [-e <exclude>] [-n <node>] [--latest] [--dry-run] [--yes] [--noemail]
```

### Parameters

| Flag | Description | Default |
|------|-------------|---------|
| `-i` | Image name and optional tag to pull (required, repeatable) | — |
| `-b` | Number of nodes pulling simultaneously | `3` |
| `-t` | Timeout in seconds per node | `1200` |
| `-e` | Comma-separated list of nodes to exclude | — |
| `-n` | Target a single specific node only | — |
| `--latest` | Resolve the most recently pushed tag from Docker Hub for each `-i` image | — |
| `--dry-run` | Check image presence per node; report what would be pulled without pulling | — |
| `--yes` | Skip the confirmation prompt before pulling | — |
| `--noemail` | Skip email notification (useful for dry-run testing) | — |

> `-n` and `-e` are mutually exclusive.

### Examples

```bash
# Pull the most recently pushed image (auto-resolves tag from Docker Hub)
./image-pull.sh \
  -i queensschoolofcomputingdocker/gpu-jupyter-latest \
  --latest \
  -b 3

# Pull a specific tagged image across all worker nodes in batches of 3
# (control-plane is auto-excluded)
./image-pull.sh \
  -i queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn-2.20.0tf-matlab-ollama-claude-qsc-u24.04-20260313 \
  -b 3

# Pull two images (new + previous) in the same run
./image-pull.sh \
  -i queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn-2.20.0tf-matlab-ollama-claude-qsc-u24.04-20260313 \
  -i queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.1cudnn-2.19.0tf-matlab-ollama-claude-qsc-u24.04-20260210 \
  -b 3

# Pull on a single node only
./image-pull.sh \
  -i queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn-2.20.0tf-matlab-ollama-claude-qsc-u24.04-20260313 \
  -n newcluster-gpunode3

# Exclude a specific worker node (e.g. a node under maintenance)
./image-pull.sh \
  -i queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn-2.20.0tf-matlab-ollama-claude-qsc-u24.04-20260313 \
  -b 3 \
  -e lobot-dev.cs.queensu.ca

# Dry-run: resolve latest tag and check which nodes already have it, without pulling
./image-pull.sh \
  -i queensschoolofcomputingdocker/gpu-jupyter-latest \
  --latest \
  -b 3 \
  --dry-run
```

### How It Works

1. If `--latest` is passed, queries the Docker Hub API for the most recently
   pushed tag of each `-i` image and resolves it before any other work begins
2. Resolves the node list, applying exclusions or targeting a single node
3. Runs a pre-flight readiness check — skips NotReady nodes and auto-excludes
   control-plane nodes (see [Node Pre-Flight Checks](#image-pull-preflight) below)
4. Launches a batch of lightweight `alpine:latest` pods simultaneously, each
   pinned to a specific node via `nodeName`
5. Each pod uses `nsenter` to run `ctr images pull` directly against the host
   containerd socket, bypassing the pod image pull mechanism entirely
6. Streams live `ctr` pull progress to the terminal while polling pod status
   silently in the background
7. After each batch completes, moves to the next batch
8. After all batches, retries any failed nodes one at a time
9. Writes a clean log file (ANSI codes and `ctr` progress lines stripped)
   alongside the full terminal output

### Node Pre-Flight Checks {#image-pull-preflight}

Before launching any pods, the script checks every node in the target list:

- **NotReady nodes** — nodes that are offline or not yet joined are skipped
  automatically. A `⚠️ NotReady, skipping` line is printed per skipped node
  and the offline count is shown in the summary.
- **Control-plane nodes** — nodes carrying the
  `node-role.kubernetes.io/control-plane` label are auto-excluded by default.
  This prevents scheduling pull pods on the control plane, where user workload
  taints (`NoSchedule`) would cause the pod to be repeatedly killed and
  restarted, breaking pod-name tracking and crashing the script. A
  `⏭️ control-plane, auto-excluded` line is printed per excluded node.
  To explicitly target a control-plane node, use `-n <node>`.

If no Ready worker nodes remain after pre-flight, the script exits immediately.

### Space Reporting

Each node's pod logs a before/after disk snapshot via `nsenter` into the host
filesystem:

```
=== Disk space before pull ===
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1       916G  412G  457G  48% /var/lib/containerd
412G    /var/lib/containerd
=== Pulling ... ===
[pull progress]
=== Disk space after pull ===
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1       916G  431G  438G  50% /var/lib/containerd
431G    /var/lib/containerd
```

The `df -h` line shows filesystem size, total used, and available space. The
`du -sh` line shows total space consumed by `/var/lib/containerd` specifically,
making it easy to see how much the pull added.

### Dry-Run Mode

When `--dry-run` is passed, no pods are launched for actual pulling. Instead:

1. A temporary `alpine:latest` pod is launched per node (with `--rm --wait=true`)
2. The pod reports current disk usage via `nsenter` (`df -h` + `du -sh /var/lib/containerd`)
3. The pod checks image presence via `ctr images ls`; results are reported per node:
   - `✅ already present — pull would be skipped`
   - `📥 not present — would pull: <image-ref>  X.X GB compressed (~Y–Z GB on disk est.)`
4. Image size estimates (compressed from Docker Hub + estimated uncompressed range) are
   shown at the top of the dry-run section and annotated on each missing image
5. A summary is printed and a dry-run email notification is sent
6. Log file is named `pull-dryrun-YYYYMMDD-HHMMSS.log`

Useful for checking which nodes still need an image and whether there is sufficient
disk space before committing to the full pull.

### Confirmation Prompt

Before launching any pods, the script prompts:

```
 Proceed with pull on N node(s)? [y/N]
```

Pass `--yes` to skip the prompt for scripted or automated runs.

### Batch Sizing Guidelines

| Cluster size | Recommended `-b` | Expected time per batch |
|---|---|---|
| 2–5 nodes | 1–2 | 5–10 min (18.7GB image) |
| 6–20 nodes | 3 | 5–7 min |
| 20+ nodes | 3–5 | 5–10 min |

On a 10G link with 2–3 Gbps usable, pulling a single 18.7GB image takes roughly
5–7 minutes. Batch size 3 means 3 simultaneous pulls sharing that bandwidth,
so allow 10–15 min per batch on large images.

### Email Notifications

Configure the block at the top of the script:

```bash
EMAIL_ENABLED=true
SMTP_SERVER="innovate.cs.queensu.ca"
SMTP_PORT=25
SMTP_USE_TLS=false
SMTP_USERNAME=""
SMTP_PASSWORD=""
FROM_EMAIL="lobot@cs.queensu.ca"
TO_EMAIL="aaron@cs.queensu.ca,whb1@queensu.ca"
```

| Variable | Description |
|----------|-------------|
| `EMAIL_ENABLED` | Set to `false` to disable all notifications |
| `SMTP_SERVER` | Hostname of the SMTP relay |
| `SMTP_PORT` | SMTP port (`25` = plain, `587` = submission+TLS) |
| `SMTP_USE_TLS` | Set to `true` to enable STARTTLS |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | Leave empty for unauthenticated relay |
| `FROM_EMAIL` | Sender address |
| `TO_EMAIL` | Recipient(s), comma-separated |

Email is sent via Python 3 `smtplib` on the control plane. The body is a
dark-themed HTML page with monospace font and a colour-coded status banner
(green for success, red for failure). Emoji in log output are colour-coded
with inline spans. Email is sent on every run — live, failed, and dry-run.

Subject line format:
- `✅ image-pull.sh complete | gpu-jupyter-latest | N node(s) pulled`
- `❌ image-pull.sh FAILED | gpu-jupyter-latest | N node(s) failed`
- `🔍 [DRY RUN] image-pull.sh | gpu-jupyter-latest | N node(s) checked`

> **Note:** `curl` SMTP does not work on this system. Python `smtplib` is used
> exclusively. Python 3 must be available on the control plane.

### Typical Workflow Before a Helm Upgrade

```bash
# 0. Dry-run to preview what will happen (recommended before every run)
#    Control-plane nodes are auto-excluded; no need to pass -e for them
./image-pull.sh -i <new-image:tag> -b 3 --dry-run
./image-cleanup.sh -i <new-image:tag> --dry-run

# 1. Pre-pull the new image across all worker nodes
./image-pull.sh -i <new-image:tag> -b 3

# 2. Run helm upgrade - nearly instant since image already cached everywhere
helm upgrade ...

# 3. Clean up old image tags after pods have migrated to new image
./image-cleanup.sh -i <new-image:tag>
```

---

## image-cleanup.sh

### Purpose

Removes old tags of an image from all cluster nodes after a helm upgrade,
freeing disk space. Automatically protects images currently in use by running
pods (e.g. long-running user sessions that haven't restarted yet).

### Usage

```bash
./image-cleanup.sh -i <image:tag> [-i <image:tag> ...] [-e <exclude>] [-n <node>] [--dry-run] [--yes] [--noemail]
```

### Parameters

| Flag | Description | Default |
|------|-------------|---------|
| `-i` | Full image name and tag to KEEP (required, repeatable) | — |
| `-e` | Comma-separated list of nodes to exclude | — |
| `-n` | Target a single specific node only | — |
| `--dry-run` | Report what would be removed per node without removing anything | — |
| `--yes` | Skip the confirmation prompt before removing images | — |
| `--noemail` | Skip email notification (useful for dry-run testing) | — |

> `-n` and `-e` are mutually exclusive.

### Examples

```bash
# Keep only the new image; remove all other old tags
# (control-plane is auto-excluded)
./image-cleanup.sh \
  -i queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn-2.20.0tf-matlab-ollama-claude-qsc-u24.04-20260313

# Keep both new and previous image; remove everything else
./image-cleanup.sh \
  -i queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn-2.20.0tf-matlab-ollama-claude-qsc-u24.04-20260313 \
  -i queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.1cudnn-2.19.0tf-matlab-ollama-claude-qsc-u24.04-20260210

# Clean a single node
./image-cleanup.sh \
  -i queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn-2.20.0tf-matlab-ollama-claude-qsc-u24.04-20260313 \
  -n newcluster-gpunode3

# Exclude a specific worker node (e.g. a node under maintenance)
./image-cleanup.sh \
  -i queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn-2.20.0tf-matlab-ollama-claude-qsc-u24.04-20260313 \
  -e lobot-dev.cs.queensu.ca

# Dry-run: see what would be removed without removing anything
./image-cleanup.sh \
  -i queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn-2.20.0tf-matlab-ollama-claude-qsc-u24.04-20260313 \
  -i queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.1cudnn-2.19.0tf-matlab-ollama-claude-qsc-u24.04-20260210 \
  --dry-run
```

### How It Works

1. Scans all running pods across all namespaces and builds a per-node map of
   which image tags are currently in use
2. Runs a pre-flight readiness check — skips NotReady nodes and auto-excludes
   control-plane nodes (see [Node Pre-Flight Checks](#image-cleanup-preflight)
   below)
3. Creates a Kubernetes ConfigMap encoding the in-use tag list per node
4. Deploys a DaemonSet using `alpine:latest` (starts in seconds, no large pull)
   with `nodeAffinity` to target or exclude specific nodes (and offline/
   control-plane nodes are always excluded from the DaemonSet affinity)
5. Each pod uses `nsenter` to run `ctr images ls` and `ctr images rm` directly
   against the host containerd
6. For each image tag removed, also removes the corresponding `sha256:` digest
   reference — this is critical for actual blob GC and disk space recovery
7. Collects logs from all pods and reports results
8. Deletes the DaemonSet and ConfigMap on completion

### Node Pre-Flight Checks {#image-cleanup-preflight}

Before generating the DaemonSet, the script checks every node in the target list:

- **NotReady nodes** — nodes that are offline or not yet joined are skipped
  automatically. A `⚠️ NotReady, skipping` line is printed per skipped node
  and the offline count is shown in the summary.
- **Control-plane nodes** — nodes carrying the
  `node-role.kubernetes.io/control-plane` label are auto-excluded by default.
  This prevents the DaemonSet from scheduling cleanup pods on the control
  plane, where user workload taints (`NoSchedule`) would cause restart loops
  that generate untrackable pod names. A `⏭️ control-plane, auto-excluded`
  line is printed per excluded node. To explicitly target a control-plane
  node, use `-n <node>`.

Offline and control-plane nodes are also added to the DaemonSet's `NotIn`
affinity so they are never scheduled even if the Kubernetes scheduler would
otherwise attempt it.

If no Ready worker nodes remain after pre-flight, the script exits immediately.

### Space Reporting

Each node's pod logs a before/after disk snapshot via `nsenter` into the host
filesystem:

```
=== Disk space before cleanup ===
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1       916G  431G  438G  50% /var/lib/containerd
431G    /var/lib/containerd
=== Images before cleanup ===
[image list]
=== Removing unused old tags ===
[removal output]
=== Images after cleanup ===
[image list]
=== Disk space after cleanup ===
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1       916G  412G  457G  48% /var/lib/containerd
412G    /var/lib/containerd
```

The `df -h` line shows filesystem-level used/available space. The `du -sh` line
shows total space consumed by `/var/lib/containerd`. Comparing before and after
shows exactly how much disk was reclaimed per node.

### Dry-Run Mode

When `--dry-run` is passed, no DaemonSet is deployed and no images are removed.
Instead:

1. The in-use image scan still runs — in-use tags are detected and reported
2. A temporary `alpine:latest` pod is launched per node to list images on that node
3. For each image found matching the image name, the action is reported:
   - `✅ Would keep:   <image-ref>` — matches the `-i` keep image
   - `⚠️  Would skip:   <image-ref>` — in use by a running pod
   - `🗑️  Would remove: <image-ref>` — old tag, would be deleted in a live run
4. A summary is printed and a dry-run email notification is sent
5. Log file is named `cleanup-dryrun-YYYYMMDD-HHMMSS.log`

Recommended before every cleanup run, particularly on clusters with active user
sessions, to confirm which images are protected by in-use detection.

### Confirmation Prompt

Before deploying the DaemonSet, the script prompts:

```
 Proceed with cleanup on N node(s)? [y/N]
```

Pass `--yes` to skip the prompt for scripted or automated runs.

### Image Protection Logic

The script protects two categories of images from removal on each node:

- **Explicitly kept**: the image tag passed via `-i`
- **In-use images**: any other tag of the same image currently referenced by a
  running pod on that node

Protected images are identified by exact full reference string match
(e.g. `docker.io/queensschoolofcomputingdocker/gpu-jupyter-latest:...`),
not by regex, to avoid mismatches on tags containing dots and hyphens.

If in-use images are found they are reported in the summary with the pod
namespace and name, enabling targeted user communication:

```
 ⚠️  Images skipped because they are in use by running pods:
  docker.io/queensschoolofcomputingdocker/gpu-jupyter-latest:...20260227
    └─ node: newcluster-gpunode3
    └─ pod:  jhub/jupyter-someuser
```

### Why Both Named Tag AND Digest Ref Must Be Removed

containerd stores images with two types of references:

```
docker.io/repo/image:tag          → named tag reference
sha256:d96404f136cf...            → digest reference
```

Both point to the same manifest digest and underlying blobs. Removing only the
named tag leaves the digest reference intact, which pins the blobs in
containerd's content store. The blobs will not be freed until ALL references
pointing to that manifest are removed. This is why a `ctr images rm` of a named
tag followed by a re-pull shows `already exists` for all layers — the data never
actually left disk.

### Email Notifications

The email configuration block is identical to the one in `image-pull.sh` — see
above for the full variable reference. The subject line format for
`image-cleanup.sh`:

- `✅ image-cleanup.sh complete | gpu-jupyter-latest | N node(s) cleaned`
- `❌ image-cleanup.sh FAILED | gpu-jupyter-latest | N failed, N timed out`
- `🔍 [DRY RUN] image-cleanup.sh | gpu-jupyter-latest | N node(s) checked`

---

## Log Files

Both scripts write log files automatically to the directory they are run from:

| Script | Live run log | Dry-run log |
|--------|-------------|-------------|
| `image-pull.sh` | `pull-results-YYYYMMDD-HHMMSS.log` | `pull-dryrun-YYYYMMDD-HHMMSS.log` |
| `image-cleanup.sh` | `cleanup-results-YYYYMMDD-HHMMSS.log` | `cleanup-dryrun-YYYYMMDD-HHMMSS.log` |

Pull logs have `ctr` progress lines and ANSI escape codes stripped (these are
only shown on the terminal). Cleanup logs are a full copy of terminal output.
Log file content is used as the body of the HTML email notification.

---

## Caveats

### Images in the `default` containerd namespace

containerd has multiple namespaces. Kubernetes uses `k8s.io`. If images were
pulled manually outside of Kubernetes (e.g. `docker pull` or `ctr pull` without
`--namespace k8s.io`), they land in the `default` namespace and are invisible
to both `crictl` and these scripts. Check with:

```bash
sudo ctr --namespace default images ls | grep <image-name>
```

Remove manually if found:
```bash
sudo ctr --namespace default images rm <image-ref>
```

### crictl vs ctr

`crictl` connects via the CRI socket and requires `/etc/crictl.yaml` to be
configured. On nodes without this config file it falls back to probing multiple
sockets and may silently fail or show no images. These scripts use `ctr`
directly which is more reliable. Do not use `crictl images` output to verify
cleanup results — use `ctr --namespace k8s.io images ls` instead.

### Interrupted pulls leave ingest debris

If a pull is cancelled mid-stream (e.g. pod killed, network drop), containerd
may leave partial data in:

```
/var/lib/containerd/io.containerd.content.v1.content/ingest/
```

This is usually cleaned up automatically on the next pull attempt. Check size
with `sudo du -sh /var/lib/containerd/io.containerd.content.v1.content/ingest/`
— if it's large and no pull is in progress, it's safe to clear manually.

### Manual cleanup after a cancelled run

If either script is interrupted (Ctrl-C, SSH disconnect, crash) before it
finishes, Kubernetes resources may be left behind. Use the commands below to
clean them up.

#### image-pull.sh — cancelled during a live run

Each node gets a pod named `image-pull-<node>-<timestamp>` in `kube-system`.
List and force-delete any that remain:

```bash
kubectl get pods -n kube-system | grep ^image-pull-
kubectl get pods -n kube-system | grep ^image-pull- | \
  awk '{print $1}' | xargs kubectl delete pod -n kube-system --force --grace-period=0
```

#### image-pull.sh — cancelled during a dry run

Dry-run check pods are named `dry-run-check-<timestamp>` and use `--rm`, so
they normally self-delete. If any remain:

```bash
kubectl get pods -n kube-system | grep ^dry-run-check-
kubectl get pods -n kube-system | grep ^dry-run-check- | \
  awk '{print $1}' | xargs kubectl delete pod -n kube-system --force --grace-period=0
```

#### image-cleanup.sh — cancelled during a live run

If interrupted before STEP 5, the DaemonSet, ConfigMap, and a local yaml file
will be left behind:

```bash
kubectl delete daemonset image-cleanup -n kube-system
kubectl delete configmap image-cleanup-inuse -n kube-system
rm -f image-cleanup-ds.yaml
```

#### image-cleanup.sh — cancelled during a dry run

Dry-run check pods are named `dry-run-check-<node>-<timestamp>` in
`kube-system`. They are deleted at the end of each node's check, but if
interrupted mid-loop:

```bash
kubectl get pods -n kube-system | grep ^dry-run-check-
kubectl get pods -n kube-system | grep ^dry-run-check- | \
  awk '{print $1}' | xargs kubectl delete pod -n kube-system --force --grace-period=0
```

### Pod scheduling timeout

The cleanup DaemonSet waits up to 120 seconds for all pods to reach `Ready`
before proceeding. On a busy cluster this may not be enough. If you see the
`WARNING: Not all pods became ready` message frequently, increase
`DS_READY_TIMEOUT` at the top of the script.

---

## Potential Improvements

### Automatic digest ref discovery
The script currently removes digest refs that share a manifest digest with the
named tag being removed. A more thorough approach would also check for
`sha256:`-prefixed refs in the `default` containerd namespace which these
scripts do not currently touch.

### Slack notification
Post a summary to a Slack channel on completion, particularly useful for the
in-use image report so admins can proactively reach out to affected users.

### Scheduled execution
Wrap both scripts in a CronJob or systemd timer that automatically runs cleanup
after each helm upgrade, using the new image tag extracted from the helm release.

### Parallel log collection
The cleanup script currently collects logs from nodes sequentially in STEP 4.
For large clusters (20+ nodes) this adds meaningful wall-clock time. Logs could
be collected in parallel with background jobs and results assembled at the end.
