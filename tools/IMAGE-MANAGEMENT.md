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
./image-pull.sh -i <image:tag> [-b <batch_size>] [-t <timeout>] [-e <exclude>] [-n <node>] [--dry-run]
```

### Parameters

| Flag | Description | Default |
|------|-------------|---------|
| `-i` | Full image name and tag to pull (required) | — |
| `-b` | Number of nodes pulling simultaneously | `3` |
| `-t` | Timeout in seconds per node | `1200` |
| `-e` | Comma-separated list of nodes to exclude | — |
| `-n` | Target a single specific node only | — |
| `--dry-run` | Check image presence per node; report what would be pulled without pulling | — |

> `-n` and `-e` are mutually exclusive.

### Examples

```bash
# Pull across all nodes in batches of 3, excluding control plane
./image-pull.sh \
  -i queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn-2.20.0tf-matlab-ollama-claude-qsc-u24.04-20260302 \
  -b 3 \
  -t 1200 \
  -e lobot-dev.cs.queensu.ca

# Pull on a single node only
./image-pull.sh \
  -i queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn-2.20.0tf-matlab-ollama-claude-qsc-u24.04-20260302 \
  -n newcluster-gpunode3

# Dry-run: check which nodes already have the image, without pulling
./image-pull.sh \
  -i queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn-2.20.0tf-matlab-ollama-claude-qsc-u24.04-20260302 \
  -b 3 \
  -e lobot-dev.cs.queensu.ca \
  --dry-run
```

### How It Works

1. Resolves the node list, applying exclusions or targeting a single node
2. Launches a batch of lightweight `alpine:latest` pods simultaneously, each
   pinned to a specific node via `nodeName`
3. Each pod uses `nsenter` to run `ctr images pull` directly against the host
   containerd socket, bypassing the pod image pull mechanism entirely
4. Streams live `ctr` pull progress to the terminal while polling pod status
   silently in the background
5. After each batch completes, moves to the next batch
6. After all batches, retries any failed nodes one at a time
7. Writes a clean log file (ANSI codes and `ctr` progress lines stripped)
   alongside the full terminal output

### Dry-Run Mode

When `--dry-run` is passed, no pods are launched for actual pulling. Instead:

1. A temporary `alpine:latest` pod is launched per node (with `--rm --wait=true`)
2. The pod runs `ctr images ls | grep -c <image>` via `nsenter` to check presence
3. Results are reported per node, grouped by batch:
   - `✅ already present — pull would be skipped`
   - `📥 not present — would pull: <image-ref>`
4. A summary is printed and a dry-run email notification is sent
5. Log file is named `pull-dryrun-YYYYMMDD-HHMMSS.log`

Useful for auditing which nodes still need a given image before committing to
the full batch run — for example, after an interrupted pull.

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
./image-pull.sh -i <new-image:tag> -b 3 -e <control-plane> --dry-run
./image-cleanup.sh -i <new-image:tag> -e <control-plane> --dry-run

# 1. Pre-pull the new image across all worker nodes
./image-pull.sh -i <new-image:tag> -b 3 -e <control-plane>

# 2. Run helm upgrade - nearly instant since image already cached everywhere
helm upgrade ...

# 3. Clean up old image tags after pods have migrated to new image
./image-cleanup.sh -i <new-image:tag> -e <control-plane>
```

---

## image-cleanup.sh

### Purpose

Removes old tags of an image from all cluster nodes after a helm upgrade,
freeing disk space. Automatically protects images currently in use by running
pods (e.g. long-running user sessions that haven't restarted yet).

### Usage

```bash
./image-cleanup.sh -i <image:tag> [-e <exclude>] [-n <node>] [--dry-run]
```

### Parameters

| Flag | Description | Default |
|------|-------------|---------|
| `-i` | Full image name and tag to KEEP (required) | — |
| `-e` | Comma-separated list of nodes to exclude | — |
| `-n` | Target a single specific node only | — |
| `--dry-run` | Report what would be removed per node without removing anything | — |

> `-n` and `-e` are mutually exclusive.

### Examples

```bash
# Clean all nodes except control plane
./image-cleanup.sh \
  -i queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn-2.20.0tf-matlab-ollama-claude-qsc-u24.04-20260302 \
  -e lobot-dev.cs.queensu.ca

# Clean a single node
./image-cleanup.sh \
  -i queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn-2.20.0tf-matlab-ollama-claude-qsc-u24.04-20260302 \
  -n newcluster-gpunode3

# Dry-run: see what would be removed without removing anything
./image-cleanup.sh \
  -i queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn-2.20.0tf-matlab-ollama-claude-qsc-u24.04-20260302 \
  -e lobot-dev.cs.queensu.ca \
  --dry-run
```

### How It Works

1. Scans all running pods across all namespaces and builds a per-node map of
   which image tags are currently in use
2. Creates a Kubernetes ConfigMap encoding the in-use tag list per node
3. Deploys a DaemonSet using `alpine:latest` (starts in seconds, no large pull)
   with `nodeAffinity` to target or exclude specific nodes
4. Each pod uses `nsenter` to run `ctr images ls` and `ctr images rm` directly
   against the host containerd
5. For each image tag removed, also removes the corresponding `sha256:` digest
   reference — this is critical for actual blob GC and disk space recovery
6. Collects logs from all pods and reports results
7. Deletes the DaemonSet and ConfigMap on completion

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

### DaemonSet cleanup on script failure

If the script is interrupted (Ctrl-C, SSH disconnect) before STEP 5, the
DaemonSet and ConfigMap will be left running. Clean up manually:

```bash
kubectl delete daemonset image-cleanup -n kube-system
kubectl delete configmap image-cleanup-inuse -n kube-system
kubectl get pods -n kube-system | grep image-pull | \
  awk '{print $1}' | xargs kubectl delete pod -n kube-system --force --grace-period=0
```

### Pod scheduling timeout

The cleanup DaemonSet waits up to 120 seconds for all pods to reach `Ready`
before proceeding. On a busy cluster this may not be enough. If you see the
`WARNING: Not all pods became ready` message frequently, increase
`DS_READY_TIMEOUT` at the top of the script.

---

## Potential Improvements

### Multi-image support
Currently targets a single image name per run. Could accept multiple `-i` flags
or a file listing images to keep, useful if multiple large images need rotation.

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

### Space reporting
Add before/after `du` of `/var/lib/containerd` to each node's log output so
the summary shows exactly how much disk space was reclaimed per node.

### Parallel log collection
The cleanup script currently collects logs from nodes sequentially in STEP 4.
For large clusters (20+ nodes) this adds meaningful wall-clock time. Logs could
be collected in parallel with background jobs and results assembled at the end.
