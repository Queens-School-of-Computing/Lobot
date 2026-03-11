# JupyterHub Config Apply Script

## Overview

A single bash script for updating the JupyterHub `config.yaml` on the control
plane without manually copying secrets between files.

- **[`apply-config.sh`](https://github.com/Queens-School-of-Computing/Lobot/blob/newcluster/tools/apply-config.sh)** — Pulls the latest config templates from GitHub, extracts secrets from the existing local `config.yaml`, substitutes them into the base template, and writes both `config.yaml` and `config-env.yaml` ready for `helm upgrade`

The script auto-detects whether it is running on the prod or dev cluster and
selects the correct environment override file automatically. The existing
`config.yaml` is always backed up before being overwritten.

---

## Config File Structure

The configuration is split into two files:

| File | Purpose |
|------|---------|
| `config.yaml.bk` | Shared base config for all environments |
| `config-prod.yaml.bk` | Prod-specific overrides (URLs, image tag, env vars) |
| `config-dev.yaml.bk` | Dev-specific overrides (URLs, image tag, env vars) |

Environment-specific values are passed to the hub via `hub.extraEnv` and read
in Python extraConfig blocks using `os.environ.get(...)`. This means there is
only one config file to maintain for most changes.

### Environment Variables Set by the Override Files

| Variable | Purpose |
|----------|---------|
| `LOBOT_RUNTIME_URL` | URL for `runtime_setting.yaml` |
| `LOBOT_ANNOUNCEMENT_URL` | URL for `announcement.yaml` |
| `LOBOT_GROUP_ROLES_URL` | URL for `group-roles.yaml` |
| `LOBOT_ANNOUNCEMENT_KEY` | Key to read from announcement YAML (`announcement_prod` or `announcement_dev`) |

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
   - hostname contains `lobot-dev` → `dev` cluster, uses `config-dev.yaml.bk`
   - otherwise → `prod` cluster, uses `config-prod.yaml.bk`
2. **Backs up** the existing `/opt/Lobot/config.yaml` to
   `/opt/Lobot/previousconfig/config_<cluster>_<YYYYMMDD_HHMMSS>.yaml`
3. **Extracts secrets** from the existing `config.yaml` using Python regex:
   - `client_id`
   - `client_secret`
   - `api_token`
   - `secretToken` (proxy token)
4. **Downloads** `config.yaml.bk` (shared base) from the GitHub raw URL via `curl`
5. **Substitutes** `xxx` placeholders in the base template with the extracted
   secret values using Python regex replacement; writes result to `config.yaml`
6. **Downloads** the environment override file (`config-prod.yaml.bk` or
   `config-dev.yaml.bk`) and writes it to `config-env.yaml`
7. **Prints** the `helm upgrade` command to run next

### Secret Placeholders

The base template uses `xxx` as a placeholder for each secret. The script
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

| Hostname (`hostname -f`) | Cluster | Base template | Env override |
|--------------------------|---------|---------------|--------------|
| contains `lobot-dev` | dev | `config.yaml.bk` | `config-dev.yaml.bk` |
| anything else | prod | `config.yaml.bk` | `config-prod.yaml.bk` |

### Backup Files

Backups are written to `/opt/Lobot/previousconfig/` and are never
automatically deleted. The directory is created if it does not exist.

| File | Example |
|------|---------|
| `config_<cluster>_<timestamp>.yaml` | `config_prod_20260309_143022.yaml` |

### Output

```
[apply-config] Cluster:  prod
[apply-config] Base template:     config.yaml.bk
[apply-config] Env override:      config-prod.yaml.bk
[apply-config] Backed up existing config to /opt/Lobot/previousconfig/config_prod_20260309_143022.yaml
[apply-config] Extracting secrets from /opt/Lobot/config.yaml...
[apply-config] Secrets extracted.
[apply-config] Fetching https://raw.githubusercontent.com/.../config.yaml.bk ...
[apply-config] Base template downloaded.
[apply-config] Applying secrets...
[apply-config] Fetching https://raw.githubusercontent.com/.../config-prod.yaml.bk ...
[apply-config] Env override written to /opt/Lobot/config-env.yaml
[apply-config] Done. Config written to /opt/Lobot/config.yaml

Review, then apply with:
  cd /opt/Lobot && RELEASE=jhub ; NAMESPACE=jhub ; helm upgrade --cleanup-on-fail $RELEASE jupyterhub/jupyterhub --namespace $NAMESPACE --version=4.0.0-beta.2 --values config.yaml --values config-env.yaml --timeout=60m
```

---

## Typical Workflow

```bash
# 0. Make changes to config.yaml.bk (and/or config-prod.yaml.bk / config-dev.yaml.bk)
#    in the repo and push to GitHub

# 1. SSH to the control plane
ssh lobot.cs.queensu.ca   # or lobot-dev.cs.queensu.ca for dev

# 2. Run the script
bash /opt/Lobot/tools/apply-config.sh

# 3. Review the generated config.yaml to confirm secrets look correct
#    and no placeholder "xxx" values remain
grep -n 'xxx' /opt/Lobot/config.yaml

# 4. Apply the helm upgrade (command is printed at the end of the script)
cd /opt/Lobot
RELEASE=jhub ; NAMESPACE=jhub ; helm upgrade --cleanup-on-fail $RELEASE \
  jupyterhub/jupyterhub --namespace $NAMESPACE \
  --version=4.0.0-beta.2 --values config.yaml --values config-env.yaml --timeout=60m
```

---

## Caveats

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

### Both --values files are required for helm upgrade

The `helm upgrade` command must always include both `--values config.yaml` and
`--values config-env.yaml`. Running with only `config.yaml` will leave the hub
without the environment-specific URLs and image tag set in the override.

### Backup directory grows over time

Backups in `/opt/Lobot/previousconfig/` accumulate on every run and are never
pruned automatically. Periodically remove old backups if disk space is a concern:

```bash
ls -lh /opt/Lobot/previousconfig/
# Remove backups older than 30 days
find /opt/Lobot/previousconfig/ -name 'config_*.yaml' -mtime +30 -delete
```
