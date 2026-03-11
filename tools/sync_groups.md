# JupyterHub Group Sync Scripts

## Overview

Three scripts for synchronising JupyterHub group membership from the
`group-roles.yaml` file in the Lobot GitHub repository. Together they ensure
that the hub's internal user and group state matches what is declared in source
control.

- **[`sync_groups.sh`](https://github.com/Queens-School-of-Computing/Lobot/blob/newcluster/tools/sync_groups.sh)** — Orchestrator: fetches the API token from Kubernetes and runs the two Python scripts in sequence
- **[`ensure_group_users.py`](https://github.com/Queens-School-of-Computing/Lobot/blob/newcluster/tools/ensure_group_users.py)** — Creates any hub user accounts referenced by the `user:` field in `group-roles.yaml` that do not yet exist
- **[`sync_group_membership.py`](https://github.com/Queens-School-of-Computing/Lobot/blob/newcluster/tools/sync_group_membership.py)** — Creates any missing hub groups and reconciles group membership to exactly match the `members:` list in `group-roles.yaml`

These scripts need to be run each time `group-roles.yaml` is modified.
Group membership in the hub admin page provides visual verification, and
enables collaboration features between users in the same group.

All three scripts support `--dry-run` mode to preview changes without
modifying anything.

---

## Prerequisites

- `kubectl` configured with cluster access (for `sync_groups.sh` only)
- Kubernetes Secret `group-manager-token` in the `jhub` namespace containing
  `JUPYTERHUB_API_TOKEN` (used by `sync_groups.sh` to retrieve the token automatically)
- Python 3 on the control plane
- Python packages: `requests`, `yaml` (`pip install requests pyyaml`)
- JupyterHub admin API token (required when running Python scripts directly)

---

## sync_groups.sh

### Purpose

Wrapper script that fetches the JupyterHub API token from Kubernetes and calls
`ensure_group_users.py` and `sync_group_membership.py` in sequence.

### Usage

```bash
# Run from /opt/Lobot/tools/ on the control plane
./sync_groups.sh [<api-url>] [<group-roles-url>] [--verbose] [--dry-run]

# Or via environment variables:
API_URL=https://lobot.cs.queensu.ca/hub/api \
GROUP_ROLES_URL=https://raw.githubusercontent.com/.../group-roles.yaml \
  ./sync_groups.sh [--verbose] [--dry-run]
```

Both positional arguments are optional — they fall back to their respective
environment variables or built-in defaults if not provided.

### Parameters

| Argument | Description | Default |
|----------|-------------|---------|
| `<api-url>` | JupyterHub base API URL (positional, optional) | `https://lobot.cs.queensu.ca/hub/api` |
| `<group-roles-url>` | URL to `group-roles.yaml` (positional, optional) | `newcluster` branch on GitHub |
| `--dry-run` | Pass through to both Python scripts; no changes are made | — |
| `--verbose` | Pass through to both Python scripts; enables HTTP request logging | — |

The second positional argument is only treated as `<group-roles-url>` if it
does not start with `--`. Any remaining arguments are forwarded to both Python
scripts unchanged.

### How It Works

1. Reads `$1` as `API_URL` if provided; falls back to `$API_URL` env var or the prod default
2. Reads `$2` as `GROUP_ROLES_URL` if provided and not a flag; falls back to
   `$GROUP_ROLES_URL` env var or the default `newcluster` branch URL
3. Fetches `JUPYTERHUB_API_TOKEN` from the `group-manager-token` Kubernetes
   Secret in the `jhub` namespace using `kubectl` + `base64 -d`
4. Runs `ensure_group_users.py` to create any missing hub user accounts
5. Runs `sync_group_membership.py` to reconcile group membership (if the
   script exists in the same directory)

### Examples

```bash
# Dry-run on prod (default URLs)
./sync_groups.sh --dry-run --verbose

# Live run on prod (default URLs)
./sync_groups.sh

# Live run on dev with explicit URLs
./sync_groups.sh \
  https://lobot-dev.cs.queensu.ca/hub/api \
  https://raw.githubusercontent.com/Queens-School-of-Computing/Lobot/newcluster-dev/group-roles.yaml

# Or via env vars for dev
API_URL=https://lobot-dev.cs.queensu.ca/hub/api \
GROUP_ROLES_URL=https://raw.githubusercontent.com/Queens-School-of-Computing/Lobot/newcluster-dev/group-roles.yaml \
  ./sync_groups.sh --dry-run
```

---

## ensure_group_users.py

### Purpose

Reads `group-roles.yaml` and ensures that every `user:` entry (the internal
hub account that owns a collaborative group server) exists as a JupyterHub
user. Creates missing users via the hub API. Does not affect group membership
or group creation.

### Usage

```bash
python3 ensure_group_users.py \
  --api-url <hub-api-url> \
  --token <api-token> \
  --group-roles-url <url-to-group-roles.yaml> \
  [--dry-run] [--verbose]
```

### Parameters

| Flag | Description | Default |
|------|-------------|---------|
| `--api-url` | JupyterHub base API URL (required) | — |
| `--token` | Admin API token. If omitted, uses `JUPYTERHUB_API_TOKEN` env var | — |
| `--group-roles-url` | URL to `group-roles.yaml` | `newcluster` branch on GitHub |
| `--dry-run` | Report what would be created without creating anything | — |
| `--verbose` / `-v` | Log each HTTP request and response code | — |

### How It Works

1. Fetches `group-roles.yaml` from the given URL
2. Iterates over each role entry; extracts the `user:` field
3. For each `user`, calls `GET /hub/api/users/<name>` to check existence
4. If the user does not exist and `--dry-run` is not set, calls
   `POST /hub/api/users/<name>` to create them
5. Prints a `[SUMMARY]` line listing all users that were created

### Output Prefixes

| Prefix | Meaning |
|--------|---------|
| `[INFO]` | User already exists or informational note |
| `[ACTION]` | User is being created |
| `[DRY-RUN]` | Action that would be taken (dry-run mode only) |
| `[HTTP]` | HTTP request/response (verbose mode only) |

---

## sync_group_membership.py

### Purpose

Reads `group-roles.yaml` and reconciles JupyterHub group membership so it
exactly matches the `members:` list for each role whose name starts with
`group-`. Adds users who are missing from a group and removes users who are
present but not listed. Creates groups that do not yet exist.

### Usage

```bash
python3 sync_group_membership.py \
  --group-roles-url <url-to-group-roles.yaml> \
  --api-url <hub-api-url> \
  --token <api-token> \
  [--prefix <prefix>] \
  [--dry-run] [--verbose]
```

### Parameters

| Flag | Description | Default |
|------|-------------|---------|
| `--group-roles-url` | URL to `group-roles.yaml` (required) | — |
| `--api-url` | JupyterHub base API URL (required) | — |
| `--token` | Admin API token. If omitted, uses `JUPYTERHUB_API_TOKEN` env var | — |
| `--prefix` | Only sync role entries whose `name` starts with this string | `group-` |
| `--dry-run` | Report what would change without modifying anything | — |
| `--verbose` | Log each HTTP request and response code | — |

### How It Works

1. Fetches `group-roles.yaml` from the given URL
2. Iterates over each role entry; skips entries whose `name` does not start
   with `--prefix`
3. For each matching group:
   - Calls `GET /hub/api/groups/<name>` to check if the group exists and
     retrieve its current member list
   - If the group does not exist, creates it via `POST /hub/api/groups/<name>`
   - Computes `to_add = desired − existing` and `to_remove = existing − desired`
   - Calls `POST /hub/api/groups/<name>/users` to add missing members
   - Calls `DELETE /hub/api/groups/<name>/users` to remove extra members

### Output Prefixes

| Prefix | Meaning |
|--------|---------|
| `[SYNC]` | Informational: desired and existing member sets |
| `[ACTION]` | Group or membership change being applied |
| `[DRY-RUN]` | Action that would be taken (dry-run mode only) |
| `[HTTP]` | HTTP request/response (verbose mode only) |

---

## group-roles.yaml Structure

The scripts read roles from the `roles:` key. Each entry relevant to group
sync follows this structure:

```yaml
roles:
- name: group-mygroup-users       # Role name; must start with "group-" for membership sync
  user: group-mygroup             # Hub user account that owns the group server
  members:
  - alice                         # Hub usernames that belong to this group
  - bob
  scopes:
  - access:servers!user={user}
  - servers!user={user}
  - read:users!user={user}
```

> **Note:** `group-roles.yaml` is automatically generated. Do not edit it
> manually — edit the source that generates it
> (`.github/scripts/generate-group-roles`) instead.

---

## Typical Workflow

```bash
# 0. Edit the source that generates group-roles.yaml and push to GitHub.
#    The CI workflow regenerates group-roles.yaml automatically.

# 1. Dry-run to preview what will change
./sync_groups.sh --dry-run --verbose

# 2. Review the output. Confirm adds/removes and any new users/groups.

# 3. Apply the changes
./sync_groups.sh

# 4. Verify in the JupyterHub admin panel under Admin → Groups
```

---

## Caveats

### Running the Python scripts directly

If you run `ensure_group_users.py` or `sync_group_membership.py` directly
(without `sync_groups.sh`), you must supply `--api-url`, `--token`, and
`--group-roles-url` yourself. The shell wrapper handles all three
automatically.

### group-roles.yaml URL selection

`sync_groups.sh` uses the `GROUP_ROLES_URL` environment variable if set,
otherwise falls back to the `newcluster` branch default.

The easiest way to pick up both URLs from the control plane environment:

```bash
export API_URL="https://$(hostname -f)/hub/api"
export GROUP_ROLES_URL=$(python3 -c "import yaml; print(yaml.safe_load(open('/opt/Lobot/config-env.yaml'))['hub']['extraEnv']['LOBOT_GROUP_ROLES_URL'])")
./sync_groups.sh
```

To override explicitly instead:

```bash
GROUP_ROLES_URL=https://raw.githubusercontent.com/Queens-School-of-Computing/Lobot/newcluster-dev/group-roles.yaml \
  ./sync_groups.sh https://lobot-dev.cs.queensu.ca/hub/api
```

If running the Python scripts manually, supply `--group-roles-url` directly.

### Membership is fully reconciled (not append-only)

`sync_group_membership.py` removes users from groups when they are no longer
listed in `group-roles.yaml`. This is intentional — group membership in the
hub should be the authoritative mirror of the YAML. A dry-run beforehand is
recommended to confirm removals are expected.

### Hub user creation is permanent

`ensure_group_users.py` creates hub users but does not delete them. Removing
a `user:` entry from `group-roles.yaml` will not remove the corresponding hub
account. Hub users must be removed manually via the admin panel or API if
needed.
