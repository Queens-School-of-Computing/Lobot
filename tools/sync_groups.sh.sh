#!/usr/bin/env bash
set -e

# Usage:
#   ./sync_groups.sh https://lobot.cs.queensu.ca/hub/api --verbose --dry-run
# or:
#   API_URL=https://lobot.cs.queensu.ca/hub/api ./sync_groups.sh --verbose --dry-run

# 1. Get API_URL from $1 or $API_URL env, with an optional default
API_URL_ARG="$1"
API_URL="${API_URL_ARG:-${API_URL:-https://lobot.cs.queensu.ca/hub/api}}"

if [ -z "$API_URL" ]; then
  echo "Usage: $0 <api-url> [extra args passed to sync scripts]" >&2
  echo "Example: $0 https://lobot.cs.queensu.ca/hub/api --verbose --dry-run" >&2
  exit 1
fi

# Drop the first arg if it was used for API_URL
if [ -n "$API_URL_ARG" ]; then
  shift
fi

EXTRA_ARGS=("$@")

# 2. Fetch token from Kubernetes Secret
TOKEN=$(kubectl get secret group-manager-token -n jhub \
  -o jsonpath='{.data.JUPYTERHUB_API_TOKEN}' | base64 -d)

# 3. URL to your group-roles.yaml
GROUP_ROLES_URL="https://raw.githubusercontent.com/Queens-School-of-Computing/Lobot/newcluster/group-roles.yaml"

echo "[sync_groups] Using API_URL=$API_URL"

# 4. Ensure group users exist
echo "[sync_groups] Running ensure_group_users.py ${EXTRA_ARGS[*]}"
python3 ensure_group_users.py \
  --api-url "$API_URL" \
  --token "$TOKEN" \
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
