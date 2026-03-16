#!/usr/bin/env bash
set -e

usage() {
  cat <<EOF
Usage:
  ./sync_groups.sh [<api-url>] [<group-roles-url>] [--dry-run] [--verbose]

Arguments:
  <api-url>          JupyterHub base API URL (positional, optional)
                     Default: https://lobot.cs.queensu.ca/hub/api
                     Override: API_URL env var

  <group-roles-url>  URL to group-roles.yaml (positional, optional)
                     Default: newcluster branch on GitHub
                     Override: GROUP_ROLES_URL env var

  --dry-run          Preview changes without modifying anything
  --verbose          Log each HTTP request and response code

Both variables can be set from the control plane environment before running:
  export API_URL="https://\$(hostname)/hub/api"
  export GROUP_ROLES_URL=\$(python3 -c "import yaml; print(yaml.safe_load(open('/opt/Lobot/config-env.yaml'))['hub']['extraEnv']['LOBOT_GROUP_ROLES_URL'])")
  ./sync_groups.sh

Examples:
  ./sync_groups.sh
  ./sync_groups.sh https://lobot.cs.queensu.ca/hub/api --dry-run --verbose
  ./sync_groups.sh https://lobot-dev.cs.queensu.ca/hub/api https://raw.githubusercontent.com/.../group-roles.yaml
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

DEFAULT_GROUP_ROLES_URL="https://raw.githubusercontent.com/Queens-School-of-Computing/Lobot/newcluster/group-roles.yaml"

# 1. Get API_URL from $1 (if not a flag) or $API_URL env or default
if [[ "${1:-}" != --* && -n "${1:-}" ]]; then
  API_URL="$1"
  shift
else
  API_URL="${API_URL:-https://lobot.cs.queensu.ca/hub/api}"
fi

# 2. Get GROUP_ROLES_URL from $1 (if not a flag) or $GROUP_ROLES_URL env or default
if [[ "${1:-}" != --* && -n "${1:-}" ]]; then
  GROUP_ROLES_URL="$1"
  shift
else
  GROUP_ROLES_URL="${GROUP_ROLES_URL:-$DEFAULT_GROUP_ROLES_URL}"
fi

EXTRA_ARGS=("$@")

# 3. Fetch token from Kubernetes Secret
TOKEN=$(kubectl get secret group-manager-token -n jhub \
  -o jsonpath='{.data.JUPYTERHUB_API_TOKEN}' | base64 -d)

echo "[sync_groups] Using API_URL=$API_URL"
echo "[sync_groups] Using GROUP_ROLES_URL=$GROUP_ROLES_URL"

# 4. Ensure group users exist
echo "[sync_groups] Running ensure_group_users.py ${EXTRA_ARGS[*]}"
python3 ensure_group_users.py \
  --api-url "$API_URL" \
  --token "$TOKEN" \
  --group-roles-url "$GROUP_ROLES_URL" \
  "${EXTRA_ARGS[@]}"

# 5. Sync group membership (if script exists)
if [ -f sync_group_membership.py ]; then
  echo "[sync_groups] Running sync_group_membership.py ${EXTRA_ARGS[*]}"
  python3 sync_group_membership.py \
    --group-roles-url "$GROUP_ROLES_URL" \
    --api-url "$API_URL" \
    --token "$TOKEN" \
    "${EXTRA_ARGS[@]}"
else
  echo "[sync_groups] sync_group_membership.py not found; skipping membership sync"
fi
