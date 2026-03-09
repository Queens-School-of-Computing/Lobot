# JupyterHub Config Apply Script

## Overview

A single bash script for updating the JupyterHub `config.yaml` on the control
plane without manually copying secrets between files.

- **[`apply-config.sh`](https://github.com/Queens-School-of-Computing/Lobot/blob/newcluster/tools/apply-config.sh)** — Pulls the latest config template from GitHub, extracts secrets from the existing local `config.yaml`, substitutes them into the template, and writes a new `config.yaml` ready for `helm upgrade`

The script auto-detects whether it is running on the prod or dev cluster and
selects the correct template file and GitHub branch automatically. The
existing `config.yaml` is always backed up before being overwritten.

---

## Prerequisites

- `kubectl` is not required by this script
- `curl` available on the control plane
- Python 3 on the control plane (used for secret extraction and substitution)
- `helm` installed (for the `helm upgrade` command printed at the end)
- An existing `/opt/Lobot/config.yaml` containing the current secrets

---

## apply-config.sh

### Purpose

Keeps `config.yaml` in sync with the template files in the repository without
requiring manual secret management. Secrets (OAuth client ID/secret, API
token, proxy secret token) live only in the local `config.yaml` and are never
committed to GitHub. The templates in the repo use `xxx` as a placeholder for
each secret value.

### Usage

```bash
# Run from the control plane
bash /opt/Lobot/tools/apply-config.sh
```

No arguments are needed. Cluster detection and template selection are fully
automatic.

### How It Works

1. **Detects the cluster** from `hostname -f`:
   - hostname contains `lobot-dev` → `dev` cluster, uses `config.yaml.dev.bk`
     from the `newcluster-dev` branch
   - otherwise → `prod` cluster, uses `config.yaml.bk` from the `newcluster`
     branch
2. **Backs up** the existing `/opt/Lobot/config.yaml` to
   `/opt/Lobot/previousconfig/config_<cluster>_<YYYYMMDD_HHMMSS>.yaml`
3. **Extracts secrets** from the existing `config.yaml` using Python regex:
   - `client_id`
   - `client_secret`
   - `api_token`
   - `secretToken` (proxy token)
4. **Downloads** the appropriate template (`.bk` file) from the GitHub raw
   URL via `curl`
5. **Substitutes** `xxx` placeholders in the template with the extracted
   secret values using Python regex replacement
6. **Writes** the result to `/opt/Lobot/config.yaml`
7. **Prints** the `helm upgrade` command to run next

### Secret Placeholders

The template files use `xxx` as a placeholder for each secret. The script
matches and replaces using the following patterns:

| Secret | Template placeholder | Extraction pattern |
|--------|---------------------|--------------------|
| GitHub OAuth client ID | `client_id: xxx` | `client_id:\s*(\S+)` |
| GitHub OAuth client secret | `client_secret: xxx` | `client_secret:\s*(\S+)` |
| JupyterHub API token | `api_token: xxx` (or quoted) | `api_token["\s:]+([a-f0-9]{10,})` |
| Proxy secret token | `secretToken: "xxx"` | `secretToken:\s*"([^"]*)"` |

> **Important:** The proxy `secretToken` is allowed to be an empty string —
> the pattern matches zero or more characters between quotes.

### Cluster / Template Selection

| Hostname (`hostname -f`) | Cluster | Template file | GitHub branch |
|--------------------------|---------|---------------|---------------|
| contains `lobot-dev` | dev | `config.yaml.dev.bk` | `newcluster-dev` |
| anything else | prod | `config.yaml.bk` | `newcluster` |

### Backup Files

Backups are written to `/opt/Lobot/previousconfig/` and are never
automatically deleted. The directory is created if it does not exist.

| File | Example |
|------|---------|
| `config_<cluster>_<timestamp>.yaml` | `config_prod_20260309_143022.yaml` |

### Output

```
[apply-config] Cluster:  prod
[apply-config] Template: config.yaml.bk
[apply-config] Backed up existing config to /opt/Lobot/previousconfig/config_prod_20260309_143022.yaml
[apply-config] Extracting secrets from /opt/Lobot/config.yaml...
[apply-config] Secrets extracted.
[apply-config] Fetching https://raw.githubusercontent.com/.../config.yaml.bk ...
[apply-config] Template downloaded.
[apply-config] Applying secrets...
[apply-config] Done. Config written to /opt/Lobot/config.yaml

Review, then apply with:
  cd /opt/Lobot && RELEASE=jhub ; NAMESPACE=jhub ; helm upgrade --cleanup-on-fail $RELEASE jupyterhub/jupyterhub --namespace $NAMESPACE --version=4.0.0-beta.2 --values config.yaml --timeout=60m
```

---

## Typical Workflow

```bash
# 0. Make changes to config.yaml.bk (and config.yaml.dev.bk) in the repo and push to GitHub

# 1. SSH to the control plane
ssh lobot.cs.queensu.ca   # or lobot-dev.cs.queensu.ca for dev

# 2. Pull the latest tools from the repo (optional — apply-config.sh downloads
#    the template directly from GitHub, so the local tools/ clone does not need
#    to be up to date for the config itself)
cd /opt/Lobot && git pull

# 3. Run the script
bash /opt/Lobot/tools/apply-config.sh

# 4. Review the generated config.yaml to confirm secrets look correct
#    and no placeholder "xxx" values remain
grep -n 'xxx' /opt/Lobot/config.yaml

# 5. Apply the helm upgrade (command is printed at the end of the script)
cd /opt/Lobot
RELEASE=jhub ; NAMESPACE=jhub ; helm upgrade --cleanup-on-fail $RELEASE \
  jupyterhub/jupyterhub --namespace $NAMESPACE \
  --version=4.0.0-beta.2 --values config.yaml --timeout=60m
```

---

## Caveats

### Config template files must stay in sync

There are two template files maintained in parallel:

| File | Cluster | Branch |
|------|---------|--------|
| `config.yaml.bk` | prod | `newcluster` |
| `config.yaml.dev.bk` | dev | `newcluster-dev` |

Any change to `config.yaml.bk` must be reflected in `config.yaml.dev.bk`
(and vice versa), with only the environment-specific values differing
(callback URLs, branch references, etc.). Both files must use `xxx` as the
placeholder for all four secret values.

### Existing config.yaml must exist

The script reads secrets from the existing `/opt/Lobot/config.yaml`. If this
file is missing or does not contain all four secret patterns, the script exits
with an error before making any changes.

### Verify no xxx placeholders remain

After the script runs, check that no `xxx` placeholder was left unsubstituted:

```bash
grep -n 'xxx' /opt/Lobot/config.yaml
```

If any remain, a secret extraction pattern did not match the existing config.
Inspect the config manually to find the discrepancy.

### Backup directory grows over time

Backups in `/opt/Lobot/previousconfig/` accumulate on every run and are never
pruned automatically. Periodically remove old backups if disk space is a concern:

```bash
ls -lh /opt/Lobot/previousconfig/
# Remove backups older than 30 days
find /opt/Lobot/previousconfig/ -name 'config_*.yaml' -mtime +30 -delete
```
